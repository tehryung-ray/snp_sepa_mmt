"""가중모멘텀 × SEPA 전략 백테스트

라이브 스크리너와 **동일한 코드 경로**로 매주 신호를 만들고, 사용자의 실제
청산 규칙으로 포지션을 운용해 성과를 측정한다.

정직성 관련 설계 (결과 해석에 직결):

  1) 펀더멘털 40점 제외
     yfinance는 현재 분기 재무만 제공한다. 2022년 시점의 매출 성장률을
     알 수 없으므로 오늘 값을 과거 판단에 쓰면 미래참조 편향이 된다.
     라이브 코드가 데이터 없을 때 쓰는 중립값(20/40)으로 고정한다.
     → 실질적으로 기술적 85점을 검증하는 것이다.

  2) 생존 편향 있음
     현재 S&P 500 구성종목 기준. 과거 편입 후 퇴출된 종목이 누락되어
     수익률이 과대평가된다. 보정 불가 — 결과에 명시한다.

  3) 미래참조 차단
     신호는 T일 종가까지만 사용하고, 체결은 T+1일 시가에 한다.

  4) 일중 체결 순서
     같은 날 고가가 익절선을, 저가가 손절선을 모두 건드린 경우 손절을
     먼저 처리한다(보수적 가정).

청산 규칙 (사용자 지정):
  1차 익절가 = (매수가 + 익절가) ÷ 2
    → 고가가 1차 익절가 도달 시 50% 매도, 손절가를 매수가(본전)로 상향
  나머지 50% → 익절가 도달 시 익절, 또는 상향된 손절가 도달 시 청산
"""

import argparse
import json
import logging
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import config
from src.universe import get_sp500_list, download_prices, get_price_matrix
from src.momentum import calc_momentum_score
from src.phase_indicators import classify_phase, calculate_relative_strength, detect_vcp_pattern
from src.sepa import score_sepa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.ERROR)

# Phase/템플릿/VCP 계산에 필요한 최소 히스토리 (252일 52주고가 + 200일선 + VCP 325일)
WINDOW = 400

# 청산 방식 — 백테스트 전용. 라이브 스크리너(src/sepa.py)는 건드리지 않는다.
#
# 기존(target)은 Phase 2 목표가를 매수가×1.30 으로 고정하고 그 지점에서 전량
# 익절한다. 상승장에서 이익만 +30% 에 잘리고 손실은 전부 받는 비대칭이
# 벤치마크 대비 드래그로 작용했다. 아래 세 방식은 고정 목표가를 없애고
# 추세가 꺾일 때까지 보유한다. 초기 손절가(SEPA 산출)는 어느 방식에서든
# 하한으로 유지된다.
EXIT_MODES = {
    "target":    "고정 익절 — 1차 50% 후 +30% 목표가 전량 (기존)",
    "ma50":      "50일선 종가 이탈 시 전량 (고정 목표가 없음)",
    "trail20":   "고점 대비 −20% 추적손절 (고정 목표가 없음)",
    "half_ma50": "1차 익절 50% 후 나머지는 50일선 이탈까지 보유",
}
TRAIL_PCT = 0.20


# ─────────────────────────────────────────────────────────────────────
# 가격 캐시
# ─────────────────────────────────────────────────────────────────────

def load_prices_cached(tickers, years, benchmark, retries=4):
    """당일 다운로드분을 디스크에 캐시한다.

    백테스트는 파라미터를 바꿔가며 여러 번 돌리게 되는데, 그때마다 500종목을
    재다운로드하면 yfinance 레이트리밋에 걸린다. 날짜+기간 단위로 캐시한다.
    """
    cache_dir = ROOT / config.CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"prices_{years}y_{datetime.now():%Y%m%d}.pkl"

    if cache.exists():
        log.info("가격 캐시 사용: %s", cache.name)
        with open(cache, "rb") as f:
            return pickle.load(f)

    delay = 30
    for attempt in range(1, retries + 1):
        prices = download_prices(tickers, years=years, benchmark=benchmark)
        if len(prices) > len(tickers) * 0.8:
            with open(cache, "wb") as f:
                pickle.dump(prices, f)
            log.info("가격 캐시 저장: %s (%d종목)", cache.name, len(prices))
            return prices
        if attempt < retries:
            log.warning("다운로드 실패/부족 (%d종목). 레이트리밋 추정 — %d초 후 재시도 (%d/%d)",
                        len(prices), delay, attempt, retries)
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"주가 다운로드 실패: {len(prices)}종목만 확보")


# ─────────────────────────────────────────────────────────────────────
# 신호 생성
# ─────────────────────────────────────────────────────────────────────

def evaluate_candidates(date, prices, close, mom_row, spy_close,
                        top_n, template_min, threshold):
    """T일 종가 기준으로 모멘텀 상위 top_n 을 SEPA 채점한다.

    라이브와 동일하게 score_sepa() 를 호출한다. fundamentals=None 이므로
    펀더멘털은 중립 20/40 으로 들어간다.
    """
    ranked = mom_row.dropna().sort_values(ascending=False)
    ranked = ranked[ranked.index != config.BENCHMARK]

    out = []
    for rank, ticker in enumerate(ranked.head(top_n).index, 1):
        pdata = prices.get(ticker)
        if pdata is None:
            continue

        hist = pdata.loc[:date]
        if len(hist) < 250:
            continue
        hist = hist.iloc[-WINDOW:]

        try:
            current_price = float(hist["Close"].iloc[-1])
            phase_info = classify_phase(hist, current_price)
            if phase_info.get("phase", 0) == 0:
                continue

            spy_hist = spy_close.loc[:date].iloc[-WINDOW:]
            rs = calculate_relative_strength(hist["Close"], spy_hist)
            vcp = detect_vcp_pattern(hist, current_price, phase_info)

            sepa = score_sepa(
                ticker=ticker, price_data=hist, current_price=current_price,
                phase_info=phase_info, rs_series=rs,
                fundamentals=None,             # ← 미래참조 차단
                vcp_data=vcp,
                template_pass_min=template_min, buy_threshold=threshold,
            )
            sepa["momentum_rank"] = rank
            sepa["momentum_score"] = float(ranked[ticker])
            out.append(sepa)
        except Exception as e:
            log.debug("%s @ %s 평가 실패: %s", ticker, date.date(), e)
            continue

    return out


# ─────────────────────────────────────────────────────────────────────
# 포트폴리오 시뮬레이션
# ─────────────────────────────────────────────────────────────────────

def run_backtest(prices, close, mom, spy_close, trading_days, sma50,
                 max_positions=5, top_n=20, initial_capital=100_000,
                 template_min=7, threshold=60, commission=0.0005,
                 exit_mode="target"):
    """일 단위 청산 점검 + 주 단위 신규 진입.

    exit_mode 는 EXIT_MODES 참조. 어느 방식이든 초기 손절가는 하한으로 남는다.
    """
    use_half = exit_mode in ("target", "half_ma50")     # 1차 50% 익절 사용
    use_target = exit_mode == "target"                  # 고정 목표가 전량 익절
    use_ma = exit_mode in ("ma50", "half_ma50")         # 50일선 종가 이탈
    use_trail = exit_mode == "trail20"                  # 고점 대비 추적손절

    cash = float(initial_capital)
    positions = {}      # ticker -> dict
    trades = []
    equity_curve = []
    signal_cache = []   # 직전 리밸런싱의 적격 종목 (T+1 시가 체결용)

    def _close_out(ticker, pos, px, date, action):
        nonlocal cash
        cash += pos["shares"] * px * (1 - commission)
        trades.append({
            "ticker": ticker, "action": action,
            "entry_date": pos["entry_date"], "exit_date": date,
            "entry": pos["entry"], "exit": px, "shares": pos["shares"],
            "pnl_pct": (px / pos["entry"] - 1) * 100,
            "half_sold": pos["half_sold"],
            "days": (date - pos["entry_date"]).days,
        })
        del positions[ticker]

    for i, date in enumerate(trading_days):

        # ── 1) 보유 포지션 청산 점검 (일 단위) ──────────────────────
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            bar = prices[ticker].loc[:date]
            if len(bar) == 0 or bar.index[-1] != date:
                continue
            row = bar.iloc[-1]
            high, low = float(row["High"]), float(row["Low"])
            open_px, close_px = float(row["Open"]), float(row["Close"])

            # 전일 종가에 확정된 이탈 신호를 오늘 시가에 체결 (T+1 규율)
            if pos.get("pending_exit"):
                _close_out(ticker, pos, open_px, date, pos["pending_exit"])
                continue

            # 추적손절선 갱신 — 고점은 항상 추적한다
            pos["high_water"] = max(pos["high_water"], high)
            if use_trail:
                pos["stop"] = max(pos["stop"], pos["high_water"] * (1 - TRAIL_PCT))

            # 손절 우선 (보수적 가정)
            # 갭하락으로 손절선을 뛰어넘으면 실제 체결은 시가다. min() 으로 처리하지
            # 않으면 손실을 과소평가하게 된다.
            if low <= pos["stop"]:
                _close_out(ticker, pos, min(open_px, pos["stop"]), date, "STOP")
                continue

            # 1차 익절 (50% 매도 + 손절가를 매수가로 상향)
            # 갭상승 시엔 시가가 더 유리하므로 max() — 익절은 갭이 이득이다.
            if use_half and not pos["half_sold"] and high >= pos["mid"]:
                half = pos["shares"] / 2
                fill = max(open_px, pos["mid"])
                cash += half * fill * (1 - commission)
                trades.append({
                    "ticker": ticker, "action": "HALF",
                    "entry_date": pos["entry_date"], "exit_date": date,
                    "entry": pos["entry"], "exit": fill, "shares": half,
                    "pnl_pct": (fill / pos["entry"] - 1) * 100,
                    "half_sold": False,
                    "days": (date - pos["entry_date"]).days,
                })
                pos["shares"] -= half
                pos["half_sold"] = True
                pos["stop"] = max(pos["stop"], pos["entry"])   # 본전으로 상향

            # 고정 목표가 전량 익절 (기존 방식에서만)
            if use_target and pos["half_sold"] and high >= pos["target"]:
                _close_out(ticker, pos, max(open_px, pos["target"]), date, "TARGET")
                continue

            # 50일선 종가 이탈 — 장중 스톱이 아니라 종가 확정 신호이므로
            # 오늘 종가에 판정하고 다음 거래일 시가에 체결한다.
            if use_ma:
                ma = sma50.at[date, ticker] if ticker in sma50.columns else np.nan
                if pd.notna(ma) and close_px < ma:
                    pos["pending_exit"] = "MA50"

        # ── 2) 직전 리밸런싱 신호를 오늘 시가에 체결 ────────────────
        if signal_cache:
            equity = cash + sum(
                p["shares"] * float(prices[t].loc[:date]["Close"].iloc[-1])
                for t, p in positions.items()
                if len(prices[t].loc[:date])
            )
            for sig in signal_cache:
                if len(positions) >= max_positions:
                    break
                ticker = sig["ticker"]
                if ticker in positions:
                    continue
                bar = prices[ticker].loc[:date]
                if len(bar) == 0 or bar.index[-1] != date:
                    continue

                entry = float(bar.iloc[-1]["Open"])
                if entry <= 0 or entry <= sig["stop_loss"]:
                    continue

                alloc = equity / max_positions
                if alloc > cash:
                    alloc = cash
                shares = alloc / entry
                if shares <= 0:
                    continue

                cash -= shares * entry * (1 + commission)
                target = sig["target"]
                positions[ticker] = {
                    "shares": shares, "entry": entry,
                    "stop": sig["stop_loss"], "target": target,
                    "mid": (entry + target) / 2,
                    "half_sold": False, "entry_date": date,
                    "high_water": entry, "pending_exit": None,
                    "sepa": sig["sepa_score"], "mom_rank": sig["momentum_rank"],
                }
            signal_cache = []

        # ── 3) 주 단위(월요일) 신호 생성 → 다음날 체결 ──────────────
        if date.weekday() == 0 and len(positions) < max_positions:
            cands = evaluate_candidates(
                date, prices, close, mom.loc[date], spy_close,
                top_n, template_min, threshold)
            eligible = [c for c in cands if c["is_buy"]]
            eligible.sort(key=lambda x: x["sepa_score"], reverse=True)
            signal_cache = eligible

        # ── 4) 자산 기록 ────────────────────────────────────────────
        pos_value = 0.0
        for t, p in positions.items():
            h = prices[t].loc[:date]
            if len(h):
                pos_value += p["shares"] * float(h["Close"].iloc[-1])
        equity_curve.append({"date": date, "equity": cash + pos_value,
                             "positions": len(positions)})

        if i % 250 == 0:
            log.info("  %s | 자산 %s | 보유 %d | 누적매매 %d",
                     date.date(), f"{cash + pos_value:,.0f}", len(positions), len(trades))

    return pd.DataFrame(equity_curve).set_index("date"), pd.DataFrame(trades)


# ─────────────────────────────────────────────────────────────────────
# 성과 지표
# ─────────────────────────────────────────────────────────────────────

def metrics(equity: pd.Series, bench: pd.Series, trades: pd.DataFrame) -> dict:
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    init = equity.iloc[0]

    def _stats(s):
        total = (s.iloc[-1] / init - 1) * 100
        cagr = ((s.iloc[-1] / init) ** (1 / years) - 1) * 100 if years > 0 else 0
        r = s.pct_change().dropna()
        sharpe = (r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0
        dd = (s - s.cummax()) / s.cummax() * 100
        # 하방편차 기반 소르티노
        downside = r[r < 0]
        sortino = (r.mean() / downside.std() * np.sqrt(252)) if len(downside) and downside.std() > 0 else 0
        return {"total_return": round(total, 2), "cagr": round(cagr, 2),
                "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
                "mdd": round(dd.min(), 2), "final": round(s.iloc[-1], 0)}

    st = _stats(equity)
    bn = _stats(bench)

    # ── 포지션(라운드트립) 단위 통계 ──────────────────────────────
    # 한 포지션은 [HALF, TARGET] 또는 [HALF, STOP] 또는 [STOP] 으로 기록된다.
    # 체결 건수로 승률을 내면 부분익절이 항상 승리로 잡혀 왜곡되므로,
    # (종목, 진입일) 로 묶어 수량가중 평균 수익률을 포지션 성과로 삼는다.
    if not len(trades):
        return {"years": round(years, 2), "strategy": st, "benchmark": bn,
                "alpha": round(st["cagr"] - bn["cagr"], 2), "positions": 0,
                "fills": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "avg_win": 0, "avg_loss": 0, "avg_days": 0,
                "profit_factor": None, "expectancy": 0, "exposure": 0.0}

    t = trades.copy()
    t["w"] = t["pnl_pct"] * t["shares"]
    grp = t.groupby(["ticker", "entry_date"]).agg(
        pnl_pct=("w", "sum"), shares=("shares", "sum"),
        days=("days", "max"), exits=("action", "count"))
    grp["pnl_pct"] = grp["pnl_pct"] / grp["shares"]

    wins = grp[grp["pnl_pct"] > 0]
    losses = grp[grp["pnl_pct"] <= 0]
    gross_w, gross_l = wins["pnl_pct"].sum(), abs(losses["pnl_pct"].sum())
    pf = (gross_w / gross_l) if gross_l > 0 else None
    wr = len(wins) / len(grp) * 100
    avg_w = float(wins["pnl_pct"].mean()) if len(wins) else 0.0
    avg_l = float(losses["pnl_pct"].mean()) if len(losses) else 0.0

    return {
        "years": round(years, 2),
        "strategy": st,
        "benchmark": bn,
        "alpha": round(st["cagr"] - bn["cagr"], 2),
        "positions": len(grp),           # 라운드트립 수
        "fills": len(trades),            # 체결 건수 (부분익절 포함)
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(wr, 1),
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "avg_days": round(float(grp["days"].mean()), 1),
        "profit_factor": round(float(pf), 2) if pf is not None else None,
        # 기대값: 1회 매매당 평균 손익률
        "expectancy": round(wr / 100 * avg_w + (1 - wr / 100) * avg_l, 2),
        "exposure": 0.0,     # 호출부에서 실제 평균 보유비율로 덮어쓴다
    }


def main():
    ap = argparse.ArgumentParser(description="가중모멘텀 × SEPA 백테스트")
    ap.add_argument("--years", type=int, default=6, help="백테스트 기간 (기본 6년)")
    ap.add_argument("--positions", type=str, default="3,5,10",
                    help="최대 보유 종목 수 (쉼표 구분)")
    ap.add_argument("--top", type=int, default=config.TOP_N, help="모멘텀 상위 N")
    ap.add_argument("--capital", type=float, default=100_000)
    ap.add_argument("--start", default=None,
                    help="백테스트 시작일 YYYY-MM-DD (구간 분할 검증용). "
                         "지정 시 --years 는 다운로드 기간에만 쓰인다.")
    ap.add_argument("--end", default=None, help="백테스트 종료일 YYYY-MM-DD")
    ap.add_argument("--label", default=None, help="요약에 기록할 구간 이름")
    ap.add_argument("--exit-modes", default="target",
                    help="청산 방식 (쉼표 구분): " + " / ".join(EXIT_MODES))
    ap.add_argument("--out", default="data/backtest")
    args = ap.parse_args()

    modes = [m.strip() for m in args.exit_modes.split(",")]
    for m in modes:
        if m not in EXIT_MODES:
            ap.error(f"알 수 없는 청산 방식: {m} (가능: {', '.join(EXIT_MODES)})")

    # ── 데이터 ────────────────────────────────────────────────────
    sp500 = get_sp500_list()
    tickers = sp500["Symbol"].tolist()
    sector_map = dict(zip(sp500["Symbol"], sp500["sector_kr"]))
    name_map = dict(zip(sp500["Symbol"], sp500["Security"]))

    # 워밍업 2년 + 백테스트 기간
    prices = load_prices_cached(tickers, args.years + 2, config.BENCHMARK)
    close = get_price_matrix(prices)
    log.info("가격 매트릭스: %d일 × %d종목", *close.shape)

    mom = calc_momentum_score(close, config.MOMENTUM_WEIGHTS, config.SKIP_RECENT_MONTH)
    spy_close = close[config.BENCHMARK]

    # 모멘텀 12개월 + 여유 = 최소 300일 확보된 시점부터 시작.
    # --start 를 주면 워밍업만 확보하고 나머지는 날짜로 자른다.
    start_idx = 300 if args.start else max(300, len(close) - int(args.years * 252))
    trading_days = close.index[start_idx:]
    if args.start:
        trading_days = trading_days[trading_days >= pd.Timestamp(args.start)]
    if args.end:
        trading_days = trading_days[trading_days <= pd.Timestamp(args.end)]
    if len(trading_days) < 60:
        log.error("구간이 너무 짧습니다: %d 거래일", len(trading_days))
        sys.exit(1)
    log.info("백테스트 구간%s: %s ~ %s (%d 거래일)",
             f" [{args.label}]" if args.label else "",
             trading_days[0].date(), trading_days[-1].date(), len(trading_days))

    # 벤치마크 (같은 구간, 동일 초기자본)
    spy_seg = spy_close.loc[trading_days]
    bench = args.capital * (spy_seg / spy_seg.iloc[0])

    # 50일선 — MA 이탈 청산에 쓴다. 매 시점 재계산하지 않도록 한 번에 구한다.
    sma50 = close.rolling(50).mean()

    results = {}
    for mode in modes:
        for mp in [int(x) for x in args.positions.split(",")]:
            key = f"{mode}|{mp}"
            log.info("=== [%s] 최대 보유 %d종목 — %s ===", mode, mp, EXIT_MODES[mode])
            eq, tr = run_backtest(
                prices, close, mom, spy_close, trading_days, sma50,
                max_positions=mp, top_n=args.top, initial_capital=args.capital,
                template_min=config.TEMPLATE_PASS_MIN,
                threshold=config.SEPA_BUY_THRESHOLD, exit_mode=mode)

            m = metrics(eq["equity"], bench, tr)
            m["exposure"] = round(float(eq["positions"].mean() / mp * 100), 1)
            m["exit_mode"] = mode
            m["max_positions"] = mp
            results[key] = {"metrics": m, "equity": eq, "trades": tr}

            s, b = m["strategy"], m["benchmark"]
            log.info("  전략  CAGR %6.2f%% | MDD %7.2f%% | Sharpe %5.2f | 최종 %s",
                     s["cagr"], s["mdd"], s["sharpe"], f"{s['final']:,.0f}")
            log.info("  SPY   CAGR %6.2f%% | MDD %7.2f%% | Sharpe %5.2f | 최종 %s",
                     b["cagr"], b["mdd"], b["sharpe"], f"{b['final']:,.0f}")
            log.info("  포지션 %d회 | 승률 %.1f%% | 평균이익 %+.1f%% / 평균손실 %+.1f%% "
                     "| PF %s | 평균보유 %.0f일 | 노출도 %.1f%%",
                     m["positions"], m["win_rate"], m["avg_win"], m["avg_loss"],
                     m["profit_factor"], m["avg_days"], m["exposure"])

    # ── 저장 ──────────────────────────────────────────────────────
    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "label": args.label,
        "period": {"start": str(trading_days[0].date()),
                   "end": str(trading_days[-1].date()),
                   "years": round((trading_days[-1] - trading_days[0]).days / 365.25, 2)},
        "universe_size": len(prices),
        "params": {
            "momentum_weights": config.MOMENTUM_WEIGHTS,
            "top_n": args.top,
            "template_min": config.TEMPLATE_PASS_MIN,
            "sepa_threshold": config.SEPA_BUY_THRESHOLD,
            "initial_capital": args.capital,
        },
        "exit_modes": {m: EXIT_MODES[m] for m in modes},
        "caveats": [
            "펀더멘털 40점은 과거 시점 데이터 확보 불가로 중립값(20/40) 고정 — 기술적 85점만 검증",
            "현재 S&P 500 구성종목 기준이라 생존 편향 있음 (수익률 과대평가)",
            "신호는 T일 종가, 체결은 T+1일 시가 — 미래참조 차단",
            "같은 날 손절·익절선을 모두 건드리면 손절 우선 (보수적)",
            "수수료/슬리피지 편도 0.05% 반영, 세금 미반영",
            "청산 방식은 백테스트에서만 비교한 것으로, 라이브 스크리너 로직은 그대로다",
        ],
        "by_run": {k: v["metrics"] for k, v in results.items()},
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    for key, r in results.items():
        safe = key.replace("|", "_")
        r["equity"].to_csv(outdir / f"equity_{safe}.csv")
        r["trades"].to_csv(outdir / f"trades_{safe}.csv", index=False)
    bench.to_frame("equity").to_csv(outdir / "equity_benchmark.csv")

    log.info("저장 완료: %s", outdir)

    # 요약 표
    print(f"\n{'청산방식':<11}{'보유':>4}{'CAGR':>9}{'MDD':>9}{'Sharpe':>8}"
          f"{'알파':>9}{'승률':>8}{'평균보유':>9}")
    print("-" * 68)
    for key in sorted(results, key=lambda k: -results[k]["metrics"]["strategy"]["cagr"]):
        m = results[key]["metrics"]
        s = m["strategy"]
        print(f"{m['exit_mode']:<11}{m['max_positions']:>4}{s['cagr']:>8.2f}%"
              f"{s['mdd']:>8.1f}%{s['sharpe']:>8.2f}{m['alpha']:>+8.2f}%"
              f"{m['win_rate']:>7.1f}%{m['avg_days']:>7.0f}일")
    b = list(results.values())[0]["metrics"]["benchmark"]
    print("-" * 68)
    print(f"{'SPY 매수보유':<11}{'—':>4}{b['cagr']:>8.2f}%{b['mdd']:>8.1f}%"
          f"{b['sharpe']:>8.2f}{'—':>9}{'—':>8}{'—':>9}")


if __name__ == "__main__":
    main()
