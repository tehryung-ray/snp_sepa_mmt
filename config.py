"""전략 파라미터 설정 — 가중모멘텀 랭킹 + SEPA 진단"""

# ── 가중 모멘텀 (snp momentum 전략과 동일) ────────────────────────────
MOMENTUM_WEIGHTS = {
    1: 12,   # 1개월 수익률 가중치
    3: 4,    # 3개월
    6: 2,    # 6개월
    12: 1,   # 12개월
}
SKIP_RECENT_MONTH = False   # True면 최근 1개월 제외하고 계산

# ── 분석 대상 ─────────────────────────────────────────────────────────
TOP_N = 20                  # 모멘텀 상위 N개에 SEPA 분석 적용
PRICE_YEARS = 2             # 다운로드할 주가 히스토리 (12M 모멘텀 + 52주고가에 최소 1.5년 필요)
BENCHMARK = "SPY"

# ── SEPA 판정 기준 (stock-screener-main과 동일) ───────────────────────
TEMPLATE_PASS_MIN = 7       # Minervini Trend Template 8개 중 통과 최소 개수
SEPA_BUY_THRESHOLD = 60     # 125점 만점 기준 매수 신호 임계값
SEPA_MAX_SCORE = 125

# ── 출력 ──────────────────────────────────────────────────────────────
DOCS_DIR = "docs"
DATA_DIR = "data/daily"
CACHE_DIR = "data/price_cache"

# ── 사이트 메타 ───────────────────────────────────────────────────────
SITE_TITLE = "S&P 500 모멘텀 × SEPA 스크리너"
SITE_DESC = "가중 모멘텀 상위 20개 종목의 미너비니 SEPA 스코어를 매일 갱신합니다."
