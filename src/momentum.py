"""가중 모멘텀 점수 및 변동성 계산

공식: score = Σ weight_m × (현재가 / m개월전_가격 - 1)
      기본 가중치 {1개월:12, 3개월:4, 6개월:2, 12개월:1}
"""

import numpy as np
import pandas as pd

# 달(month) → 거래일 수
_MONTH_TO_DAYS = {1: 21, 3: 63, 6: 126, 12: 252}


def calc_momentum_score(close: pd.DataFrame,
                        weights: dict,
                        skip_recent: bool = False) -> pd.DataFrame:
    """날짜별·종목별 가중 모멘텀 점수를 계산한다.

    Args:
        close: DataFrame (Date × Ticker) — 종가 매트릭스
        weights: {개월수: 가중치} 예) {1:12, 3:4, 6:2, 12:1}
        skip_recent: True면 최근 1개월(21거래일)을 제외하고 수익률 산출
                     (단기 평균회귀 노이즈 제거용)

    Returns:
        DataFrame (Date × Ticker) — 모멘텀 점수. 데이터 부족 구간은 NaN.
    """
    skip_days = _MONTH_TO_DAYS[1] if skip_recent else 0

    score = pd.DataFrame(0.0, index=close.index, columns=close.columns)

    for months, weight in weights.items():
        period = _MONTH_TO_DAYS.get(months, months * 21)

        if skip_days > 0:
            # 1개월 전 → (1M + N개월) 전 구간 수익률
            ret = close.shift(skip_days) / close.shift(skip_days + period) - 1
        else:
            # 현재 → N개월 전 수익률
            ret = close / close.shift(period) - 1

        score = score.add(ret * weight, fill_value=0)

    # 어느 한 구간이라도 데이터가 없으면 점수를 신뢰할 수 없으므로 NaN 처리
    longest = max(_MONTH_TO_DAYS.get(m, m * 21) for m in weights) + skip_days
    valid = close.shift(longest).notna()
    score = score.where(valid)

    return score


def calc_volatility(close: pd.DataFrame, window: int = 63) -> pd.DataFrame:
    """63거래일(약 3개월) 롤링 연율화 변동성."""
    daily_ret = close.pct_change()
    return daily_ret.rolling(window).std() * np.sqrt(252)


def rank_latest(mom_scores: pd.DataFrame,
                exclude: list = None,
                top_n: int = 20) -> list:
    """최종 거래일 기준 모멘텀 랭킹 상위 N개를 반환한다.

    Returns:
        [{'rank': 1, 'ticker': 'XYZ', 'score': 3.21}, ...]
    """
    exclude = set(exclude or [])
    latest = mom_scores.iloc[-1].dropna()
    latest = latest[~latest.index.isin(exclude)]
    latest = latest.sort_values(ascending=False)

    return [
        {"rank": i + 1, "ticker": t, "momentum_score": round(float(v), 4)}
        for i, (t, v) in enumerate(latest.head(top_n).items())
    ]
