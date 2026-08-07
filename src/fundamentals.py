"""분기 펀더멘털 수집 — SEPA 채점에 필요한 항목만

상위 N개 종목에만 적용하므로 캐시 없이 매 실행 시 yfinance에서 직접 조회한다.
(20종목 기준 약 20~40초)
"""

import logging
import math
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)


def _pct_change(latest, base) -> Optional[float]:
    """NaN·0 방어 처리된 변화율(%)."""
    try:
        if latest is None or base is None:
            return None
        if math.isnan(latest) or math.isnan(base) or base == 0:
            return None
        return (latest - base) / abs(base) * 100
    except (TypeError, ValueError):
        return None


def fetch_fundamentals(ticker: str) -> Dict:
    """단일 종목의 분기 재무 지표를 가져온다.

    Returns:
        quarterly_revenue, revenue_qoq_change, revenue_yoy_change,
        eps_yoy_change, inventory_qoq_change, gross_margin, market_cap 등
        실패 시 빈 dict.
    """
    result: Dict = {"ticker": ticker}

    try:
        stock = yf.Ticker(ticker)
        income = stock.quarterly_financials
        balance = stock.quarterly_balance_sheet
    except Exception as e:
        log.warning("%s 재무 조회 실패: %s", ticker, e)
        return {}

    if income is None or income.empty:
        log.warning("%s 분기 손익 데이터 없음", ticker)
        return {}

    # ── 매출 ──────────────────────────────────────────────────────────
    if "Total Revenue" in income.index:
        rev = income.loc["Total Revenue"].sort_index()
        # 날짜 인덱스를 문자열로 (JSON 직렬화용)
        result["quarterly_revenue"] = {
            str(k.date()) if hasattr(k, "date") else str(k): float(v)
            for k, v in rev.items() if not pd.isna(v)
        }
        if len(rev) >= 2:
            result["revenue_qoq_change"] = _pct_change(rev.iloc[-1], rev.iloc[-2])
        if len(rev) >= 5:
            result["revenue_yoy_change"] = _pct_change(rev.iloc[-1], rev.iloc[-5])

    # ── EPS ───────────────────────────────────────────────────────────
    eps_key = next((k for k in ("Diluted EPS", "Basic EPS") if k in income.index), None)
    if eps_key:
        eps = income.loc[eps_key].sort_index()
        if len(eps) >= 2:
            result["eps_qoq_change"] = _pct_change(eps.iloc[-1], eps.iloc[-2])
        if len(eps) >= 5:
            result["eps_yoy_change"] = _pct_change(eps.iloc[-1], eps.iloc[-5])

    # ── 매출총이익률 ──────────────────────────────────────────────────
    if "Gross Profit" in income.index and "Total Revenue" in income.index:
        gp = income.loc["Gross Profit"].sort_index()
        rv = income.loc["Total Revenue"].sort_index()
        if len(gp) and len(rv) and rv.iloc[-1]:
            margin = gp.iloc[-1] / rv.iloc[-1] * 100
            if not pd.isna(margin):
                result["gross_margin"] = round(float(margin), 2)
                if len(gp) >= 2 and rv.iloc[-2]:
                    prev = gp.iloc[-2] / rv.iloc[-2] * 100
                    if not pd.isna(prev):
                        result["margin_change"] = round(float(margin - prev), 2)

    # ── 재고 ──────────────────────────────────────────────────────────
    if balance is not None and not balance.empty and "Inventory" in balance.index:
        inv = balance.loc["Inventory"].sort_index()
        if len(inv) >= 2:
            result["inventory_qoq_change"] = _pct_change(inv.iloc[-1], inv.iloc[-2])

    return result


def fetch_many(tickers: list) -> Dict[str, Dict]:
    """여러 종목의 펀더멘털을 순차 조회한다 (yfinance 레이트리밋 회피)."""
    out = {}
    for i, ticker in enumerate(tickers, 1):
        log.info("[%d/%d] 펀더멘털 조회: %s", i, len(tickers), ticker)
        out[ticker] = fetch_fundamentals(ticker)
    return out
