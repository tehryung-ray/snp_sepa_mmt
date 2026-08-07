"""SEPA 진단 스코어러 (게이트 없음)

stock-screener-main의 `score_buy_signal()`은 Phase 2가 아니거나 Trend Template
7/8 미달이면 즉시 0점으로 반환한다. 이 모듈은 동일한 배점 체계를 쓰되 조기
반환을 제거해, 모멘텀 상위 종목이 어떤 Phase에 있든 **점수 내역을 항상** 볼 수
있게 한다. 매수 적격 여부는 `is_buy` / `blocked_reason`으로 따로 표시한다.

배점 (125점 만점) — 원본과 동일:
    추세 구조 40 · 펀더멘털 40 · 손익비 15 · 상대강도 10 · 거래량 10 · 진입 5 · VCP 5
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .phase_indicators import (
    calculate_sma,
    calculate_rs_slope,
    detect_breakout,
    validate_minervini_trend_template,
)

log = logging.getLogger(__name__)


# 8개 Trend Template 조건의 한글 라벨 (표시용)
CRITERIA_LABELS = [
    ("price_above_150_200", "주가 > 150일선 · 200일선"),
    ("sma_150_above_200", "150일선 > 200일선"),
    ("sma_200_rising", "200일선 1개월 이상 상승"),
    ("sma_50_above_150", "50일선 > 150일선"),
    ("price_above_50", "주가 > 50일선"),
    ("price_30pct_above_52w_low", "52주 저가 대비 +30% 이상"),
    ("price_near_52w_high", "52주 고가 대비 -25% 이내"),
    ("confirmed_stage_2", "Phase 2 (확정 상승추세)"),
]


def _score_trend(phase: int, phase_info: Dict, price_data: pd.DataFrame,
                 current_price: float, vcp_data: Optional[Dict],
                 reasons: list) -> tuple:
    """추세 구조 점수 (40점) — 이격도·기울기·돌파·과열 페널티."""
    distance_50 = phase_info.get("distance_from_50sma", 0)
    distance_200 = phase_info.get("distance_from_200sma", 0)
    slope_50 = phase_info.get("slope_50", 0)
    slope_200 = phase_info.get("slope_200", 0)

    trend_score = 0.0

    # A) 이동평균 위 이격도 (15점) — 음수 이격은 0점으로 클램프
    distance_component = min(15, max(0,
        (distance_50 / 15.0 * 10) + (distance_200 / 20.0 * 5)
    ))
    trend_score += distance_component

    if distance_50 >= 10:
        reasons.append(f"강한 상승추세: 50일선 +{distance_50:.1f}%")
    elif distance_50 >= 3:
        reasons.append(f"양호한 상승추세: 50일선 +{distance_50:.1f}%")
    elif distance_50 >= 0:
        reasons.append(f"약한 상승추세: 50일선 +{distance_50:.1f}%")
    else:
        reasons.append(f"⚠ 50일선 이탈: {distance_50:.1f}%")

    # B) 이동평균 기울기 (15점)
    slope_component = min(15, max(0,
        (slope_50 / 0.08 * 10) + (slope_200 / 0.05 * 5)
    ))
    trend_score += slope_component

    if slope_50 > 0.05:
        reasons.append(f"이평선 강한 상승 (50:{slope_50:.3f} / 200:{slope_200:.3f})")
    elif slope_50 > 0.02:
        reasons.append("이평선 완만한 상승")
    elif slope_50 > 0:
        reasons.append("이평선 미약한 상승")
    else:
        reasons.append("⚠ 이평선 횡보 또는 하락")

    # C) 돌파 (10점)
    breakout_info = detect_breakout(price_data, current_price, phase_info, vcp_data)
    if breakout_info["is_breakout"]:
        trend_score += 10
        btype = breakout_info["breakout_type"]
        if breakout_info.get("volume_confirmed"):
            reasons.append(f"🟢 {btype} (거래량 확인)")
        else:
            reasons.append(f"🟡 {btype} (거래량 미확인)")

    # D) 과열 페널티 (최대 -10점)
    if distance_50 > 30:
        trend_score -= 10
        reasons.append(f"⚠ 과열: 50일선 +{distance_50:.1f}%")
    elif distance_50 > 20:
        trend_score -= 5
        reasons.append(f"다소 과열: 50일선 +{distance_50:.1f}%")

    return max(0.0, min(trend_score, 40.0)), breakout_info


def _score_fundamentals(fundamentals: Optional[Dict], reasons: list) -> float:
    """펀더멘털 점수 (40점) — 매출 15 · EPS 15 · 재고 10."""
    if not fundamentals:
        reasons.append("펀더멘털 데이터 없음 (중립 배점)")
        return 20.0

    score = 0.0

    # A) 매출 성장 (15점)
    quarterly_revenue = fundamentals.get("quarterly_revenue") or {}
    revenue_yoy = fundamentals.get("revenue_yoy_change")

    if len(quarterly_revenue) >= 4:
        rev = pd.Series(quarterly_revenue).sort_index()
        q1 = ((rev.iloc[-1] - rev.iloc[-2]) / rev.iloc[-2] * 100) if rev.iloc[-2] else 0
        q2 = ((rev.iloc[-2] - rev.iloc[-3]) / rev.iloc[-3] * 100) if rev.iloc[-3] else 0
        q3 = ((rev.iloc[-3] - rev.iloc[-4]) / rev.iloc[-4] * 100) if rev.iloc[-4] else 0
        avg_qoq = (q1 + q2 + q3) / 3.0

        rev_score = 0.0 if avg_qoq <= 0 else min(15, (avg_qoq / 10.0) * 15)

        if q1 < -2:
            # 최근 분기 역성장은 강한 감점
            score -= 15
            reasons.append(f"🔴 매출: 최근 분기 {q1:.1f}% 감소 (3Q 평균 {avg_qoq:.1f}%, 감점)")
        elif avg_qoq >= 5:
            reasons.append(f"🟢 매출: 3Q 평균 {avg_qoq:.1f}% QoQ ({q3:.1f}% → {q2:.1f}% → {q1:.1f}%)")
        elif avg_qoq >= 0:
            reasons.append(f"🟡 매출: 3Q 평균 {avg_qoq:.1f}% QoQ ({q3:.1f}% → {q2:.1f}% → {q1:.1f}%)")
        else:
            reasons.append(f"🔴 매출: 3Q 평균 {avg_qoq:.1f}% QoQ")
        score += rev_score
    elif revenue_yoy:
        if revenue_yoy <= 0:
            reasons.append(f"🔴 매출: {revenue_yoy:.0f}% YoY 감소")
        else:
            score += min(15, (revenue_yoy / 20.0) * 15)
            mark = "🟢" if revenue_yoy >= 10 else "🟡"
            reasons.append(f"{mark} 매출: {revenue_yoy:.0f}% YoY")
    else:
        reasons.append("🔴 매출 데이터 없음")

    # B) EPS 성장 (15점) — -20% → 0점, 0% → 3.75점, +60% → 15점
    eps_yoy = fundamentals.get("eps_yoy_change")
    if eps_yoy:
        score += min(15, max(0, ((eps_yoy + 20) / 80.0) * 15))
        if eps_yoy >= 50:
            reasons.append(f"🟢 EPS: +{eps_yoy:.0f}% YoY (강한 이익 성장)")
        elif eps_yoy >= 20:
            reasons.append(f"🟢 EPS: +{eps_yoy:.0f}% YoY")
        elif eps_yoy >= 0:
            reasons.append(f"🟡 EPS: +{eps_yoy:.0f}% YoY")
        else:
            reasons.append(f"🔴 EPS: {eps_yoy:.0f}% YoY")
    else:
        score += 7.5   # 데이터 없으면 중립

    # C) 재고 (10점) — 재고 감소 = 수요 강함
    inv_qoq = fundamentals.get("inventory_qoq_change")
    if inv_qoq is not None:
        score += min(10, max(0, 10 - (inv_qoq / 20.0) * 10))
        if inv_qoq < -5:
            reasons.append(f"✓ 재고 감소 ({inv_qoq:.1f}% QoQ — 수요 강함)")
        elif inv_qoq < 5:
            reasons.append(f"재고 중립 ({inv_qoq:.1f}% QoQ)")
        elif inv_qoq < 15:
            reasons.append(f"⚠ 재고 증가 ({inv_qoq:.1f}% QoQ)")
        else:
            reasons.append(f"⚠ 재고 급증 ({inv_qoq:.1f}% QoQ — 수요 둔화 우려)")
    else:
        score += 5     # 재고 개념이 없는 업종 다수 → 중립

    # D) 마진 (10점) — 원본과 동일하게 중립 고정
    score += 10

    return max(0.0, min(score, 40.0))


def _score_volume(price_data: pd.DataFrame, reasons: list) -> float:
    """거래량 점수 (10점) — 상승일 거래량 / 하락일 거래량 비율."""
    if "Volume" not in price_data.columns or len(price_data) < 30:
        return 5.0

    recent_prices = price_data["Close"].iloc[-6:]
    recent_volume = price_data["Volume"].iloc[-5:]

    up_days = down_days = 0
    vol_up = vol_down = 0.0

    for i in range(1, len(recent_prices)):
        change = recent_prices.iloc[i] - recent_prices.iloc[i - 1]
        vol = recent_volume.iloc[i - 1]
        if change > 0:
            up_days += 1
            vol_up += vol
        else:
            down_days += 1
            vol_down += vol

    avg_up = vol_up / up_days if up_days else 0
    avg_down = vol_down / down_days if down_days else 0
    ratio = (avg_up / avg_down) if avg_down > 0 else 1.0

    score = min(10, max(0, 5 + (ratio - 1.0) * 10))

    if ratio >= 1.3:
        reasons.append(f"✓ 상승일 거래량 우위 (비율 {ratio:.2f})")
    elif ratio >= 1.1:
        reasons.append(f"상승일 거래량 소폭 우위 (비율 {ratio:.2f})")
    elif ratio >= 0.9:
        reasons.append(f"거래량 중립 (비율 {ratio:.2f})")
    else:
        reasons.append(f"⚠ 하락일 거래량 우위 (비율 {ratio:.2f} — 분산 매도)")

    return score


def _score_rs(rs_series: pd.Series, reasons: list) -> tuple:
    """상대강도 점수 (10점) — SPY 대비 20일 RS 기울기."""
    if rs_series is None or len(rs_series) < 20 or rs_series.isna().all():
        return 5.0, None

    rs_slope = calculate_rs_slope(rs_series, 20)
    score = min(10, max(0, 5 + (rs_slope * 16.67)))

    if rs_slope > 0.10:
        reasons.append(f"✓ 강한 상대강도: {rs_slope:.3f} (SPY 대비 초과수익)")
    elif rs_slope > 0.03:
        reasons.append(f"양(+)의 상대강도: {rs_slope:.3f}")
    elif rs_slope > -0.03:
        reasons.append(f"중립 상대강도: {rs_slope:.3f}")
    elif rs_slope > -0.10:
        reasons.append(f"약한 상대강도: {rs_slope:.3f}")
    else:
        reasons.append(f"⚠ 상대강도 하락: {rs_slope:.3f} (SPY 대비 부진)")

    return score, round(rs_slope, 3)


def calculate_stop_loss(price_data: pd.DataFrame, current_price: float,
                        phase_info: Dict, phase: int) -> float:
    """논리적 손절가 산출 (원본 로직 그대로).

    Phase 2: 최근 10일 저가 또는 50일선 중 높은 쪽 (타이트한 손절)
    그 외  : 최근 30일 베이스 저점
    공통   : 위험폭 3~10% 범위로 강제
    """
    sma_50 = phase_info.get("sma_50", 0)

    if phase == 2:
        recent_low = price_data["Low"].iloc[-10:].min() if len(price_data) >= 10 \
            else price_data["Low"].min()
        swing_stop = recent_low * 0.995
        sma_stop = sma_50 * 0.99 if sma_50 > 0 else swing_stop
        stop = max(swing_stop, sma_stop)

        risk = (current_price - stop) / current_price
        if risk < 0.03:
            stop = current_price * 0.97
        elif risk > 0.10:
            stop = current_price * 0.90
    else:
        base_low = price_data["Low"].iloc[-30:].min() if len(price_data) >= 30 \
            else price_data["Low"].min()
        stop = base_low * 0.99
        if (current_price - stop) / current_price > 0.10:
            stop = current_price * 0.90

    return stop


def _score_risk_reward(current_price: float, stop_loss: float, phase: int,
                       phase_info: Dict, breakout_info: Dict,
                       reasons: list) -> tuple:
    """손익비 점수 (15점) — 2:1 미만은 0점, 5:1 이상 만점."""
    risk = current_price - stop_loss

    if phase == 2:
        target = current_price * 1.30
    elif breakout_info.get("is_breakout"):
        target = breakout_info["breakout_level"] * 1.25
    else:
        sma_50 = phase_info.get("sma_50", 0)
        target = sma_50 * 1.25 if sma_50 > 0 else current_price * 1.25

    reward = target - current_price

    if risk <= 0 or reward <= 0:
        return 0.0, 0.0, target, risk

    rr = reward / risk
    score = 0.0 if rr < 2.0 else min(15, ((rr - 2.0) * 6) + 3)

    if rr >= 5.0:
        reasons.append(f"🟢 탁월한 손익비: {rr:.1f}:1 (상승 ${reward:.2f} / 위험 ${risk:.2f})")
    elif rr >= 4.0:
        reasons.append(f"🟢 우수한 손익비: {rr:.1f}:1")
    elif rr >= 3.0:
        reasons.append(f"🟢 양호한 손익비: {rr:.1f}:1")
    elif rr >= 2.0:
        reasons.append(f"🟡 수용 가능한 손익비: {rr:.1f}:1")
    else:
        reasons.append(f"🔴 부족한 손익비: {rr:.1f}:1 (최소 2:1 필요)")

    return score, round(rr, 2), target, risk


def _score_entry(phase: int, phase_info: Dict, current_price: float,
                 reasons: list) -> tuple:
    """진입 품질 점수 (5점) — 미너비니 피벗 포인트 방법론.

    Phase 2·3(주도주 국면): 52주 고가 근접도 3점 + 50일선 이격 2점
    Phase 1·4(베이스 국면): 50일선 돌파 지점 근접도 5점 환산
    """
    week_52_high = phase_info.get("week_52_high", current_price)
    distance_50 = phase_info.get("distance_from_50sma", 0)
    gap_52w = ((current_price - week_52_high) / week_52_high * 100) if week_52_high > 0 else -100

    entry_score = 0.0

    if phase in (2, 3):
        # 52주 고가 근접도 (3점)
        if gap_52w >= -5:
            entry_score += 3
            reasons.append(f"🟢 52주 고가권: 고가 대비 {abs(gap_52w):.1f}% (피벗 존)")
        elif gap_52w >= -15:
            entry_score += 3 - ((abs(gap_52w) - 5) / 10.0)
            reasons.append(f"🟢 52주 고가 근접: 고가 대비 {abs(gap_52w):.1f}%")
        elif gap_52w >= -25:
            entry_score += 2 - ((abs(gap_52w) - 15) / 10.0)
            reasons.append(f"🟡 52주 고가 25% 이내: 고가 대비 {abs(gap_52w):.1f}%")
        else:
            reasons.append(f"🔴 52주 고가에서 이탈: 고가 대비 {abs(gap_52w):.1f}% (주도주 아님)")

        # 50일선 이격 (2점)
        if 0 < distance_50 <= 20:
            entry_score += 2 - (distance_50 / 20.0)
        elif distance_50 > 20:
            entry_score += max(0, 1 - ((distance_50 - 20) / 15.0))
    else:
        # 돌파 지점(50일선 +1%) 근접도
        deviation = abs(distance_50 - 1.0)
        entry_score += max(0, 2 - (deviation / 6.0) * 2)

        if -1 <= distance_50 <= 3:
            reasons.append(f"✓ 최적 돌파 구간: 50일선 {distance_50:.1f}%")
        elif -4 <= distance_50 <= 6:
            reasons.append(f"양호한 진입 구간: 50일선 {distance_50:.1f}%")
        else:
            reasons.append(f"진입 구간 이탈: 50일선 {distance_50:.1f}%")

    return min(5.0, max(0.0, entry_score)), round(gap_52w, 1)


def _score_vcp(vcp_data: Optional[Dict], reasons: list) -> float:
    """VCP 보너스 (5점) — 변동성 수축 패턴 품질에 따라 1/3/5점."""
    if not vcp_data or not vcp_data.get("is_vcp"):
        if vcp_data and vcp_data.get("contraction_count", 0) > 0:
            reasons.append(f"🟡 부분 패턴: {vcp_data.get('pattern_details', '')}")
        return 0.0

    quality = vcp_data.get("vcp_quality", 0)
    detail = vcp_data.get("pattern_details", "")

    if quality >= 80:
        reasons.append(f"⭐ VCP 패턴: {detail} (품질 {quality:.0f}/100)")
        return 5.0
    if quality >= 60:
        reasons.append(f"🟢 VCP 패턴: {detail} (품질 {quality:.0f}/100)")
        return 3.0
    reasons.append(f"🟡 VCP 패턴: {detail} (품질 {quality:.0f}/100)")
    return 1.0


def score_sepa(ticker: str,
               price_data: pd.DataFrame,
               current_price: float,
               phase_info: Dict,
               rs_series: pd.Series,
               fundamentals: Optional[Dict] = None,
               vcp_data: Optional[Dict] = None,
               template_pass_min: int = 7,
               buy_threshold: int = 60) -> Dict:
    """SEPA 종합 점수를 계산한다. Phase에 관계없이 항상 전 항목을 채점한다.

    Returns:
        점수 내역 · Trend Template 8개 조건 · 손절/익절가 · 매수 적격 여부
    """
    phase = phase_info.get("phase", 0)
    reasons: list = []

    # Minervini Trend Template (8개 조건) — 순수 SEPA 점수
    sma_200_series = calculate_sma(price_data["Close"], 200)
    template = validate_minervini_trend_template(current_price, phase_info, sma_200_series)

    # 각 항목 채점
    trend_score, breakout_info = _score_trend(
        phase, phase_info, price_data, current_price, vcp_data, reasons)
    fundamental_score = _score_fundamentals(fundamentals, reasons)
    volume_score = _score_volume(price_data, reasons)
    rs_score, rs_slope = _score_rs(rs_series, reasons)

    stop_loss = calculate_stop_loss(price_data, current_price, phase_info, phase)
    rr_score, rr_ratio, target, risk = _score_risk_reward(
        current_price, stop_loss, phase, phase_info, breakout_info, reasons)

    entry_score, gap_52w = _score_entry(phase, phase_info, current_price, reasons)
    vcp_score = _score_vcp(vcp_data, reasons)

    total = (trend_score + fundamental_score + volume_score + rs_score
             + rr_score + entry_score + vcp_score)
    total = max(0.0, min(total, 125.0))

    # 매수 적격 판정 — 원본 게이트를 여기서만 적용
    passes_template = template["criteria_passed"] >= template_pass_min
    blocked = None
    if phase != 2:
        blocked = f"Phase {phase} (미너비니는 Phase 2만 매수)"
    elif not passes_template:
        blocked = f"Trend Template {template['criteria_passed']}/8 (최소 {template_pass_min} 필요)"
    elif total < buy_threshold:
        blocked = f"SEPA {total:.0f}점 (임계값 {buy_threshold} 미달)"

    # 1차 익절가 = (현재가 + 익절가) ÷ 2 — 절반 익절 후 손절가를 매수가로 이동
    mid_target = (current_price + target) / 2 if target > current_price else None

    return {
        "ticker": ticker,
        "phase": phase,
        "phase_name": phase_info.get("phase_name", ""),
        "phase_confidence": phase_info.get("confidence", 0),
        "sepa_score": round(total, 1),
        "is_buy": blocked is None,
        "blocked_reason": blocked,
        "template_score": template["template_score"],
        "criteria_passed": template["criteria_passed"],
        "criteria_details": template["criteria_details"],
        "passes_template": passes_template,
        "components": {
            "trend": round(trend_score, 1),
            "fundamental": round(fundamental_score, 1),
            "risk_reward": round(rr_score, 1),
            "relative_strength": round(rs_score, 1),
            "volume": round(volume_score, 1),
            "entry": round(entry_score, 1),
            "vcp": round(vcp_score, 1),
        },
        "current_price": round(current_price, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target, 2),
        "mid_target": round(mid_target, 2) if mid_target else None,
        "risk_amount": round(risk, 2),
        "risk_reward_ratio": rr_ratio,
        "rs_slope": rs_slope,
        "gap_from_52w_high": gap_52w,
        "sma_50": phase_info.get("sma_50"),
        "sma_200": phase_info.get("sma_200"),
        "vcp_quality": vcp_data.get("vcp_quality") if vcp_data else None,
        "is_vcp": bool(vcp_data and vcp_data.get("is_vcp")),
        "breakout": breakout_info.get("breakout_type") if breakout_info.get("is_breakout") else None,
        "reasons": reasons,
    }


# 컴포넌트 만점 (표시용)
COMPONENT_MAX = {
    "trend": 40,
    "fundamental": 40,
    "risk_reward": 15,
    "relative_strength": 10,
    "volume": 10,
    "entry": 5,
    "vcp": 5,
}

COMPONENT_LABELS = {
    "trend": "추세 구조",
    "fundamental": "펀더멘털",
    "risk_reward": "손익비",
    "relative_strength": "상대강도",
    "volume": "거래량",
    "entry": "진입 품질",
    "vcp": "VCP",
}
