"""S&P 500 유니버스 수집 + 주가 다운로드"""

import io
import logging
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

log = logging.getLogger(__name__)

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# GICS 11개 섹터 → 한글 축약 (stock-screener-main 뱃지와 동일한 표기)
GICS_KR = {
    "Information Technology": "IT",
    "Health Care": "헬스",
    "Financials": "금융",
    "Consumer Discretionary": "소비재",
    "Communication Services": "통신",
    "Industrials": "산업재",
    "Consumer Staples": "생필품",
    "Energy": "에너지",
    "Utilities": "유틸",
    "Real Estate": "리츠",
    "Materials": "소재",
}


def get_sp500_list() -> pd.DataFrame:
    """Wikipedia에서 S&P 500 구성종목을 가져온다.

    Returns:
        DataFrame[Symbol, Security, GICS Sector, GICS Sub-Industry, sector_kr]
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    r = requests.get(WIKI_URL, headers=headers, timeout=20)
    r.raise_for_status()

    tables = pd.read_html(io.StringIO(r.text))
    df = tables[0][["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()

    # BRK.B → BRK-B (yfinance 표기)
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
    df["sector_kr"] = df["GICS Sector"].map(GICS_KR).fillna("기타")

    log.info("S&P 500 구성종목: %d개", len(df))
    return df


def download_prices(tickers: list, years: int = 2,
                    benchmark: str = "SPY") -> dict:
    """여러 종목의 일봉 OHLCV를 배치 다운로드한다.

    Returns:
        {ticker: DataFrame(Open, High, Low, Close, Volume)}
    """
    end = datetime.now() + timedelta(days=1)          # yfinance end는 exclusive
    start = end - timedelta(days=years * 365 + 45)

    all_tickers = list(dict.fromkeys(list(tickers) + [benchmark]))
    log.info("주가 다운로드: %d종목 × %d년", len(all_tickers), years)

    raw = yf.download(
        all_tickers,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    prices, failed = {}, []
    for ticker in all_tickers:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                df = raw.xs(ticker, level="Ticker", axis=1).copy()
            else:
                df = raw.copy()
            df = df.dropna(subset=["Close"])
            if len(df) < 200:          # Phase 분류에 200일 필요
                failed.append(ticker)
                continue
            prices[ticker] = df
        except Exception:
            failed.append(ticker)

    log.info("다운로드 완료: 성공 %d, 제외 %d", len(prices), len(failed))
    if failed:
        log.warning("데이터 부족/실패 (일부): %s", failed[:10])

    return prices


def get_price_matrix(prices: dict) -> pd.DataFrame:
    """각 종목 Close를 하나의 DataFrame(Date × Ticker)으로 합친다."""
    matrix = pd.DataFrame({t: df["Close"] for t, df in prices.items()})
    return matrix.sort_index()
