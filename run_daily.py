"""S&P 500 가중모멘텀 × SEPA 스크리너 — 일일 실행 엔트리포인트

흐름:
  1. Wikipedia에서 S&P 500 구성종목 수집
  2. 전 종목 2년 일봉 배치 다운로드
  3. 가중 모멘텀 점수 산출 → 상위 N개 선정
  4. 상위 N개에 대해 Phase 분류 · VCP · 펀더멘털 → SEPA 점수 채점
  5. JSON 저장 + GitHub Pages용 HTML 생성

사용:
  python run_daily.py                    # 기본 (config.TOP_N)
  python run_daily.py --top 30           # 상위 30개
  python run_daily.py --no-fundamentals  # 펀더멘털 생략 (빠른 테스트)
"""

import argparse
import json
import logging
import sys
from datetime import datetime, date
from pathlib import Path

import numpy as np

# Windows 콘솔 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import config
from src.universe import get_sp500_list, download_prices, get_price_matrix
from src.momentum import calc_momentum_score, rank_latest
from src.phase_indicators import (
    classify_phase,
    calculate_relative_strength,
    detect_vcp_pattern,
)
from src.sepa import score_sepa
from src.fundamentals import fetch_many
from src.report import build_html

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.ERROR)


def _json_safe(obj):
    """numpy 스칼라·Timestamp를 파이썬 기본 타입으로 변환 (json.dumps default)."""
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        val = float(obj)
        return None if np.isnan(val) else val
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):          # pandas.Timestamp
        return obj.isoformat()
    raise TypeError(f"직렬화 불가 타입: {type(obj).__name__}")


def analyze_market(prices: dict, benchmark: str) -> dict:
    """벤치마크(SPY)의 현재 국면을 요약한다."""
    spy = prices.get(benchmark)
    if spy is None or len(spy) < 200:
        return {}

    price = float(spy["Close"].iloc[-1])
    info = classify_phase(spy, price)
    return {
        "ticker": benchmark,
        "price": round(price, 2),
        "phase": info.get("phase"),
        "phase_name": info.get("phase_name"),
        "confidence": info.get("confidence"),
        "sma_50": info.get("sma_50"),
        "sma_200": info.get("sma_200"),
        "distance_from_50sma": info.get("distance_from_50sma"),
    }


def run(top_n: int, with_fundamentals: bool = True) -> dict:
    sp500 = get_sp500_list()
    tickers = sp500["Symbol"].tolist()

    name_map = dict(zip(sp500["Symbol"], sp500["Security"]))
    sector_map = dict(zip(sp500["Symbol"], sp500["sector_kr"]))
    gics_map = dict(zip(sp500["Symbol"], sp500["GICS Sector"]))

    prices = download_prices(tickers, years=config.PRICE_YEARS,
                             benchmark=config.BENCHMARK)
    close = get_price_matrix(prices)
    log.info("가격 매트릭스: %d일 × %d종목", *close.shape)

    # ── 1) 가중 모멘텀 랭킹 ──────────────────────────────────────────
    mom = calc_momentum_score(close, config.MOMENTUM_WEIGHTS,
                              config.SKIP_RECENT_MONTH)
    ranking = rank_latest(mom, exclude=[config.BENCHMARK], top_n=top_n)
    log.info("모멘텀 상위 %d개 선정: %s", top_n,
             ", ".join(r["ticker"] for r in ranking[:10]) + " ...")

    # ── 2) 펀더멘털 (상위 N개만) ─────────────────────────────────────
    top_tickers = [r["ticker"] for r in ranking]
    fundamentals = fetch_many(top_tickers) if with_fundamentals else {}

    # ── 3) SEPA 채점 ─────────────────────────────────────────────────
    spy_close = close[config.BENCHMARK] if config.BENCHMARK in close.columns else None
    results = []

    for entry in ranking:
        ticker = entry["ticker"]
        pdata = prices.get(ticker)
        if pdata is None or len(pdata) < 200:
            log.warning("%s: 데이터 부족, 건너뜀", ticker)
            continue

        try:
            current_price = float(pdata["Close"].iloc[-1])
            phase_info = classify_phase(pdata, current_price)

            if phase_info.get("phase", 0) == 0:
                log.warning("%s: Phase 분류 불가, 건너뜀", ticker)
                continue

            rs_series = (calculate_relative_strength(pdata["Close"], spy_close)
                         if spy_close is not None else None)
            vcp = detect_vcp_pattern(pdata, current_price, phase_info)

            sepa = score_sepa(
                ticker=ticker,
                price_data=pdata,
                current_price=current_price,
                phase_info=phase_info,
                rs_series=rs_series,
                fundamentals=fundamentals.get(ticker),
                vcp_data=vcp,
                template_pass_min=config.TEMPLATE_PASS_MIN,
                buy_threshold=config.SEPA_BUY_THRESHOLD,
            )

            sepa.update({
                "rank": entry["rank"],
                "momentum_score": entry["momentum_score"],
                "name": name_map.get(ticker, ticker),
                "sector": sector_map.get(ticker, "기타"),
                "gics_sector": gics_map.get(ticker, "Unknown"),
            })
            results.append(sepa)

            log.info("  #%-2d %-6s 모멘텀 %.2f | Phase %d | Template %d/8 | SEPA %.1f%s",
                     entry["rank"], ticker, entry["momentum_score"],
                     sepa["phase"], sepa["criteria_passed"], sepa["sepa_score"],
                     "  ✅매수" if sepa["is_buy"] else "")

        except Exception as e:
            log.error("%s 분석 실패: %s", ticker, e)
            continue

    scan_date = close.index[-1].strftime("%Y-%m-%d")

    return {
        "scan_date": scan_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "universe_size": len(prices),
        "top_n": top_n,
        "momentum_weights": config.MOMENTUM_WEIGHTS,
        "market": analyze_market(prices, config.BENCHMARK),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="S&P 500 가중모멘텀 × SEPA 스크리너")
    parser.add_argument("--top", type=int, default=config.TOP_N,
                        help=f"SEPA 분석 대상 상위 종목 수 (기본 {config.TOP_N})")
    parser.add_argument("--no-fundamentals", action="store_true",
                        help="펀더멘털 조회 생략 (빠른 테스트용)")
    parser.add_argument("--output", default=None,
                        help="HTML 출력 경로 (기본 docs/index.html)")
    args = parser.parse_args()

    data = run(args.top, with_fundamentals=not args.no_fundamentals)

    if not data["results"]:
        log.error("분석 결과가 비어 있습니다. 중단.")
        sys.exit(1)

    # JSON 저장
    data_dir = ROOT / config.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    for path in (data_dir / "latest.json",
                 data_dir / f"scan_{data['scan_date']}.json"):
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=_json_safe),
            encoding="utf-8")
    log.info("JSON 저장: %s", data_dir / "latest.json")

    # HTML 생성
    out_path = Path(args.output) if args.output else ROOT / config.DOCS_DIR / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html(data), encoding="utf-8")
    log.info("HTML 저장: %s", out_path)

    buys = sum(1 for r in data["results"] if r["is_buy"])
    log.info("=== 완료 ===  분석 %d개 · 매수 적격 %d개",
             len(data["results"]), buys)


if __name__ == "__main__":
    main()
