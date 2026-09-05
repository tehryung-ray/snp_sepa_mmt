"""GitHub Pages용 HTML 리포트 생성

정보 설계 원칙:
  - 요약을 먼저, 상세는 접어서 (시장 국면 → 랭킹 → 종목별 내역)
  - 8개 Trend Template 조건을 점 8개로 인코딩 → 20종목을 한눈에 비교
  - SEPA 점수 막대에 매수 임계선(60점)을 표시해 합격/불합격이 형태로 보이게
"""

import html
from datetime import datetime
from typing import Dict, List
from urllib.parse import quote

from .sepa import CRITERIA_LABELS, COMPONENT_MAX, COMPONENT_LABELS

PHASE_META = {
    1: ("베이스", "p1"),
    2: ("상승추세", "p2"),
    3: ("분산·과열", "p3"),
    4: ("하락추세", "p4"),
}

_CSS = """
:root{
  --bg:#0b1220; --panel:#131c2e; --panel2:#1a2438; --line:#26324a;
  --ink:#e6ecf7; --ink2:#94a3b8; --ink3:#64748b;
  --accent:#f5a524;           /* 모멘텀 = 열기 */
  --good:#34d399; --warn:#fbbf24; --bad:#f87171; --info:#60a5fa;
}
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',
    'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
  background:var(--bg); color:var(--ink); line-height:1.55;
  -webkit-font-smoothing:antialiased; font-size:15px;
}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
.num{font-variant-numeric:tabular-nums}

/* ── 헤더 ───────────────────────────────────────────── */
header{
  background:linear-gradient(160deg,#16203a 0%,#0e1728 100%);
  border-bottom:1px solid var(--line); padding:30px 16px 26px;
}
.eyebrow{
  font-size:11px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin-bottom:8px
}
h1{font-size:clamp(21px,4.4vw,29px);font-weight:800;letter-spacing:-.02em;text-wrap:balance}
.sub{margin-top:7px;font-size:13px;color:var(--ink2)}
.sub b{color:var(--ink);font-weight:600}

/* ── 시장 요약 ──────────────────────────────────────── */
.market{
  display:grid;grid-template-columns:minmax(190px,1.25fr) repeat(4,1fr);
  gap:10px;margin:22px 0 26px
}
.mcard{
  background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px 15px
}
.mcard.spy{border-color:#3b5680;background:linear-gradient(150deg,#17253d,#131c2e)}
.mlabel{font-size:10.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3)}
.mval{font-size:23px;font-weight:800;letter-spacing:-.02em;margin-top:3px}
.mnote{font-size:11.5px;color:var(--ink2);margin-top:3px}
.mcard.spy .mnote{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}

/* ── 섹션 ───────────────────────────────────────────── */
.sec{margin:30px 0}
.sec-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.sec h2{font-size:17px;font-weight:800;letter-spacing:-.01em}
.sec-note{font-size:12.5px;color:var(--ink2)}

/* ── 랭킹 행 ────────────────────────────────────────── */
.cols{
  display:grid;
  grid-template-columns:34px 108px 66px 62px 84px 96px 1fr 108px;
  gap:10px;align-items:center
}
.colhead{
  padding:0 14px 7px;font-size:10.5px;font-weight:700;letter-spacing:.07em;
  text-transform:uppercase;color:var(--ink3);border-bottom:1px solid var(--line)
}
.row{
  background:var(--panel);border:1px solid var(--line);border-radius:11px;
  margin-top:7px;overflow:hidden
}
.row.buy{border-color:#2f6b52;background:linear-gradient(100deg,#13251d 0%,var(--panel) 42%)}
.row>summary{padding:12px 14px;cursor:pointer;list-style:none}
.row>summary::-webkit-details-marker{display:none}
.row>summary:hover{background:var(--panel2)}
.row[open]>summary{background:var(--panel2);border-bottom:1px solid var(--line)}

.rank{font-size:17px;font-weight:800;color:var(--accent);text-align:center}
.tk{font-size:16px;font-weight:800;letter-spacing:-.01em}
.tk .nm{display:block;font-size:11px;font-weight:400;color:var(--ink3);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* 티커 → 토스증권 종목 페이지 */
.tk a.toss{color:inherit;text-decoration:none;border-bottom:1px dashed #46587a}
.tk a.toss:after{content:'↗';font-size:9px;margin-left:3px;vertical-align:super;
  color:var(--ink3);font-weight:400}
.tk a.toss:hover{color:var(--accent);border-bottom-color:var(--accent)}
.tk a.toss:hover:after{color:var(--accent)}
.tk a.toss:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:3px}
.sect{
  display:inline-block;font-size:11px;font-weight:700;padding:2.5px 7px;
  border-radius:5px;background:#22304a;color:#a9bdd9;white-space:nowrap
}
.mom{font-size:15px;font-weight:700;color:var(--accent)}
.mom small{display:block;font-size:10px;font-weight:400;color:var(--ink3);letter-spacing:.04em}

.phase{
  display:inline-block;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;
  white-space:nowrap
}
.p1{background:#1e3a5f;color:#7dd3fc}
.p2{background:#14432f;color:#6ee7b7}
.p3{background:#42320c;color:#fcd34d}
.p4{background:#451a1a;color:#fca5a5}

/* 8개 조건 점 */
.dots{display:flex;gap:3px;align-items:center}
.dot{width:9px;height:9px;border-radius:2px;background:#31405c}
.dot.on{background:var(--good)}
.dots .cnt{margin-left:5px;font-size:11.5px;font-weight:700;color:var(--ink2)}

/* SEPA 점수 막대 */
.bar{position:relative;height:19px;background:#1d2941;border-radius:4px;overflow:hidden}
.bar>i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;display:block}
.bar .mark{position:absolute;top:0;bottom:0;width:2px;background:#6b7ea0;opacity:.85}
.bar .txt{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:flex-end;
  padding-right:7px;font-size:11.5px;font-weight:800;color:#fff;
  text-shadow:0 1px 2px rgba(0,0,0,.6)
}
.barnote{font-size:10px;color:var(--ink3);margin-top:2px;letter-spacing:.03em}

.px{text-align:right;font-size:14px;font-weight:700}
.px small{display:block;font-size:10.5px;font-weight:400;color:var(--ink3);margin-top:1px}

/* ── 상세 ───────────────────────────────────────────── */
.detail{padding:15px 15px 17px;background:#101828}
.dgrid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.dtitle{
  font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);margin-bottom:9px
}
.comp{display:flex;align-items:center;gap:9px;margin-bottom:6px;font-size:12.5px}
.comp .cn{width:60px;flex-shrink:0;color:var(--ink2)}
.comp .cb{flex:1;height:7px;background:#1d2941;border-radius:3px;overflow:hidden}
.comp .cb>i{display:block;height:100%;background:var(--info);border-radius:3px}
.comp .cv{width:56px;flex-shrink:0;text-align:right;font-weight:700}

.crit{display:flex;align-items:center;gap:7px;margin-bottom:4px;font-size:12.5px}
.crit .ck{width:14px;flex-shrink:0;font-weight:800;text-align:center}
.crit.ok .ck{color:var(--good)}
.crit.no .ck{color:var(--bad)}
.crit.no span{color:var(--ink3)}

.plan{
  display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0 12px;
  padding:11px;background:var(--panel);border:1px solid var(--line);border-radius:9px
}
.plan div{text-align:center}
.plan .pl{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3)}
.plan .pv{font-size:15px;font-weight:800;margin-top:2px}
.pv.stop{color:var(--bad)} .pv.mid{color:var(--warn)} .pv.tgt{color:var(--good)}

.why{list-style:none;font-size:12.5px;color:var(--ink2)}
.why li{padding:2.5px 0 2.5px 13px;position:relative}
.why li:before{content:'';position:absolute;left:2px;top:11px;width:4px;height:4px;
  border-radius:50%;background:var(--ink3)}
.block{
  margin-top:11px;padding:8px 11px;border-radius:7px;font-size:12.5px;
  background:#2a1c14;border:1px solid #5a3a1e;color:#fcd34d
}
.block.pass{background:#122b21;border-color:#2f6b52;color:#6ee7b7}

/* ── 푸터 ───────────────────────────────────────────── */
footer{
  margin-top:44px;padding:24px 16px 32px;border-top:1px solid var(--line);
  background:#0a101c;font-size:12px;color:var(--ink3)
}
footer p{margin-bottom:5px}
footer b{color:var(--ink2)}

/* ── 모바일 ─────────────────────────────────────────── */
@media (max-width:820px){
  .market{grid-template-columns:1fr 1fr}
  .mcard.spy{grid-column:1/-1}
  .mcard.spy .mnote{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
  .colhead{display:none}
  .cols{grid-template-columns:30px 1fr auto;grid-template-areas:
    "rank tk   phase"
    "rank sect mom"
    "dots dots dots"
    "bar  bar  bar"
    "px   px   px";
    gap:5px 9px}
  .cols>.rank{grid-area:rank;align-self:start;padding-top:2px}
  .cols>.tk{grid-area:tk}
  .cols>.sectwrap{grid-area:sect}
  .cols>.momwrap{grid-area:mom;text-align:right}
  .cols>.phasewrap{grid-area:phase;text-align:right}
  .cols>.dotswrap{grid-area:dots;margin-top:5px}
  .dotswrap:before{
    content:'트렌드 템플릿';font-size:10px;font-weight:700;letter-spacing:.06em;
    color:var(--ink3);margin-right:7px
  }
  .dots{display:inline-flex;vertical-align:middle}
  .cols>.barwrap{grid-area:bar;margin-top:3px}
  .cols>.pxwrap{grid-area:px;display:flex;gap:14px;align-items:baseline;
    justify-content:flex-start;margin-top:6px;text-align:left}
  .px small{display:inline;margin:0}
  .px{text-align:left}
  .dgrid{grid-template-columns:1fr;gap:16px}
  .plan{grid-template-columns:repeat(2,1fr)}
}
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _toss_url(ticker: str) -> str:
    """토스증권 종목 페이지 URL.

    토스는 원본 표기(점)를 쓴다: BRK.B ✓ / BRK-B ✗ / BRKB ✗
    universe.py 가 yfinance 용으로 `.` → `-` 변환을 하므로 여기서 되돌린다.
    미국 티커에 고유 하이픈은 없으므로 역변환은 정확하다.
    """
    symbol = ticker.replace("-", ".").upper()
    return f"https://tossinvest.com/stocks/{quote(symbol, safe='.')}"


def _fmt(v, digits=2, dash="—"):
    if v is None:
        return dash
    return f"{v:,.{digits}f}"


def _score_color(score: float, threshold: int = 60) -> str:
    if score >= 90:
        return "var(--good)"
    if score >= threshold:
        return "#5eb894"
    if score >= threshold * 0.75:
        return "var(--warn)"
    return "#7a8699"


def _dots(criteria: Dict) -> str:
    """8개 Trend Template 조건을 점으로 인코딩."""
    cells = "".join(
        f'<i class="dot{" on" if criteria.get(key) else ""}"></i>'
        for key, _ in CRITERIA_LABELS
    )
    passed = sum(1 for key, _ in CRITERIA_LABELS if criteria.get(key))
    return f'<div class="dots">{cells}<span class="cnt">{passed}/8</span></div>'


def _bar(score: float, max_score: int, threshold: int) -> str:
    pct = max(0.0, min(100.0, score / max_score * 100))
    mark = threshold / max_score * 100
    color = _score_color(score, threshold)
    return (
        f'<div class="bar">'
        f'<i style="width:{pct:.1f}%;background:{color}"></i>'
        f'<span class="mark" style="left:{mark:.1f}%"></span>'
        f'<span class="txt num">{score:.0f}</span>'
        f'</div>'
        f'<div class="barnote">/{max_score} · 매수선 {threshold}</div>'
    )


def _components(comp: Dict) -> str:
    rows = []
    for key, maximum in COMPONENT_MAX.items():
        val = comp.get(key, 0)
        pct = (val / maximum * 100) if maximum else 0
        rows.append(
            f'<div class="comp">'
            f'<span class="cn">{COMPONENT_LABELS[key]}</span>'
            f'<span class="cb"><i style="width:{pct:.0f}%"></i></span>'
            f'<span class="cv num">{val:g}<small style="color:var(--ink3)">/{maximum}</small></span>'
            f'</div>'
        )
    return "".join(rows)


def _criteria(criteria: Dict) -> str:
    rows = []
    for key, label in CRITERIA_LABELS:
        ok = bool(criteria.get(key))
        rows.append(
            f'<div class="crit {"ok" if ok else "no"}">'
            f'<span class="ck">{"✓" if ok else "✕"}</span>'
            f'<span>{_esc(label)}</span>'
            f'</div>'
        )
    return "".join(rows)


def _row(r: Dict, threshold: int, max_score: int) -> str:
    phase_label, phase_cls = PHASE_META.get(r["phase"], ("—", "p1"))
    buy_cls = " buy" if r["is_buy"] else ""

    # 매수 계획
    plan = (
        '<div class="plan">'
        f'<div><div class="pl">현재가</div><div class="pv num">${_fmt(r["current_price"])}</div></div>'
        f'<div><div class="pl">손절가</div><div class="pv stop num">${_fmt(r["stop_loss"])}</div></div>'
        f'<div><div class="pl">1차 익절</div><div class="pv mid num">${_fmt(r.get("mid_target"))}</div></div>'
        f'<div><div class="pl">최종 익절</div><div class="pv tgt num">${_fmt(r["target"])}</div></div>'
        '</div>'
    )

    if r["is_buy"]:
        verdict = '<div class="block pass">✅ 매수 적격 — Phase 2 · Trend Template 통과 · SEPA 임계값 충족</div>'
    else:
        verdict = f'<div class="block">⏸ 매수 보류 — {_esc(r["blocked_reason"])}</div>'

    reasons = "".join(f"<li>{_esc(x)}</li>" for x in r.get("reasons", []))

    extras = []
    if r.get("rs_slope") is not None:
        extras.append(f'RS 기울기 {r["rs_slope"]:+.3f}')
    if r.get("risk_reward_ratio"):
        extras.append(f'손익비 {r["risk_reward_ratio"]:.1f}:1')
    if r.get("gap_from_52w_high") is not None:
        extras.append(f'52주고가 대비 {r["gap_from_52w_high"]:+.1f}%')
    if r.get("is_vcp"):
        extras.append(f'VCP 품질 {r["vcp_quality"]:.0f}/100')
    if r.get("breakout"):
        extras.append(_esc(r["breakout"]))
    extras_html = (' · '.join(extras)) if extras else ''

    return f"""
<details class="row{buy_cls}">
  <summary>
    <div class="cols">
      <div class="rank num">{r["rank"]}</div>
      <div class="tk"><a class="toss" href="{_toss_url(r["ticker"])}"
           target="_blank" rel="noopener noreferrer"
           title="토스증권에서 {_esc(r["ticker"])} 보기">{_esc(r["ticker"])}</a><span
           class="nm">{_esc(r["name"])}</span></div>
      <div class="sectwrap"><span class="sect">{_esc(r["sector"])}</span></div>
      <div class="momwrap mom num">{_fmt(r["momentum_score"])}<small>모멘텀</small></div>
      <div class="phasewrap"><span class="phase {phase_cls}">P{r["phase"]} {phase_label}</span></div>
      <div class="dotswrap">{_dots(r["criteria_details"])}</div>
      <div class="barwrap">{_bar(r["sepa_score"], max_score, threshold)}</div>
      <div class="pxwrap px num">${_fmt(r["current_price"])}
        <small>손절 ${_fmt(r["stop_loss"])}</small></div>
    </div>
  </summary>
  <div class="detail">
    {plan}
    <div class="dgrid">
      <div>
        <div class="dtitle">SEPA 점수 구성</div>
        {_components(r["components"])}
      </div>
      <div>
        <div class="dtitle">미너비니 트렌드 템플릿 {r["criteria_passed"]}/8</div>
        {_criteria(r["criteria_details"])}
      </div>
    </div>
    {f'<div class="dtitle" style="margin-top:16px">주요 지표</div><div style="font-size:12.5px;color:var(--ink2)">{extras_html}</div>' if extras_html else ''}
    <div class="dtitle" style="margin-top:16px">채점 근거</div>
    <ul class="why">{reasons}</ul>
    {verdict}
  </div>
</details>"""


def build_html(data: Dict) -> str:
    """스캔 결과 dict → GitHub Pages용 완성 HTML."""
    results: List[Dict] = data["results"]
    threshold = 60
    max_score = 125

    total = len(results)
    buys = sum(1 for r in results if r["is_buy"])
    tmpl_pass = sum(1 for r in results if r["passes_template"])
    avg_sepa = (sum(r["sepa_score"] for r in results) / total) if total else 0
    phase2 = sum(1 for r in results if r["phase"] == 2)

    mk = data.get("market") or {}
    if mk:
        m_label, m_cls = PHASE_META.get(mk.get("phase"), ("—", "p1"))
        spy_card = f"""
    <div class="mcard spy">
      <div class="mlabel">시장 기준 · SPY</div>
      <div class="mval num">${_fmt(mk.get("price"))}</div>
      <div class="mnote"><span class="phase {m_cls}">P{mk.get("phase")} {m_label}</span>
        <span class="num">신뢰도 {mk.get("confidence", 0):.0f}% · 50일선 {mk.get("distance_from_50sma", 0):+.1f}%</span></div>
    </div>"""
    else:
        spy_card = '<div class="mcard spy"><div class="mlabel">시장 기준 · SPY</div><div class="mval">—</div></div>'

    w = data.get("momentum_weights", {})
    weight_str = " + ".join(f"{v}×{k}개월" for k, v in sorted(w.items(), key=lambda x: int(x[0])))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = "".join(_row(r, threshold, max_score) for r in results)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>모멘텀 × SEPA 스크리너 | {_esc(data['scan_date'])}</title>
<meta name="description" content="S&amp;P 500 가중 모멘텀 상위 {total}개 종목의 미너비니 SEPA 스코어">
<style>{_CSS}</style>
</head>
<body>

<header>
  <div class="wrap">
    <div class="eyebrow">S&amp;P 500 · Momentum × SEPA</div>
    <h1>가중 모멘텀 상위 {total}개의 SEPA 점검</h1>
    <p class="sub">기준일 <b>{_esc(data['scan_date'])}</b> · 유니버스 <b>{data.get('universe_size', 0)}종목</b>
      · 모멘텀 가중치 <b>{_esc(weight_str)}</b></p>
  </div>
</header>

<div class="wrap">

  <div class="market">
    {spy_card}
    <div class="mcard">
      <div class="mlabel">매수 적격</div>
      <div class="mval num" style="color:var(--good)">{buys}<small style="font-size:14px;color:var(--ink3)">/{total}</small></div>
      <div class="mnote">Phase 2 + 템플릿 + {threshold}점</div>
    </div>
    <div class="mcard">
      <div class="mlabel">템플릿 통과</div>
      <div class="mval num">{tmpl_pass}<small style="font-size:14px;color:var(--ink3)">/{total}</small></div>
      <div class="mnote">8개 조건 중 7개 이상</div>
    </div>
    <div class="mcard">
      <div class="mlabel">Phase 2</div>
      <div class="mval num">{phase2}<small style="font-size:14px;color:var(--ink3)">/{total}</small></div>
      <div class="mnote">확정 상승추세 국면</div>
    </div>
    <div class="mcard">
      <div class="mlabel">평균 SEPA</div>
      <div class="mval num">{avg_sepa:.0f}<small style="font-size:14px;color:var(--ink3)">/{max_score}</small></div>
      <div class="mnote">상위 {total}개 평균</div>
    </div>
  </div>

  <section class="sec">
    <div class="sec-head">
      <h2>모멘텀 랭킹 × SEPA 점수</h2>
      <span class="sec-note">행을 눌러 점수 구성과 8개 조건을 펼쳐 보세요 · 티커 ↗ 를 누르면 토스증권으로 이동합니다</span>
    </div>

    <div class="cols colhead">
      <div>#</div><div>종목</div><div>섹터</div><div>모멘텀</div>
      <div>국면</div><div>템플릿</div><div>SEPA 점수</div><div style="text-align:right">현재가</div>
    </div>

    {rows}
  </section>

</div>

<footer>
  <div class="wrap">
    <p><b>랭킹 기준</b> — 가중 모멘텀 = {_esc(weight_str)} 수익률의 가중합. S&amp;P 500 전 종목을 매일 재계산합니다.</p>
    <p><b>SEPA 점수</b> — 추세 40 · 펀더멘털 40 · 손익비 15 · 상대강도 10 · 거래량 10 · 진입 5 · VCP 5 (총 {max_score}점).
       마크 미너비니 <i>Trade Like a Stock Market Wizard</i>의 트렌드 템플릿과 SEPA 방법론 기반.</p>
    <p><b>매수 적격</b> — Phase 2 · 트렌드 템플릿 7/8 이상 · SEPA {threshold}점 이상을 모두 만족한 경우에만 표시됩니다.
       모멘텀 상위라도 대부분은 여기서 걸러집니다.</p>
    <p><b>종목 코드</b> — 티커를 누르면 토스증권 해당 종목 페이지가 새 탭으로 열립니다. 행의 나머지 부분을 누르면 상세가 펼쳐집니다.</p>
    <p style="margin-top:12px">갱신 {now} · 데이터 yfinance / Wikipedia</p>
    <p style="color:#4a5568">본 페이지는 정보 제공 목적이며 투자 자문이 아닙니다. 과거 성과는 미래 수익을 보장하지 않습니다.</p>
  </div>
</footer>

<script>
// 티커 링크는 <summary> 안에 있어, 클릭이 그대로 버블링되면 행까지 함께
// 펼쳐진다. 링크 클릭만 따로 처리해 토글을 막는다.
document.querySelectorAll('a.toss').forEach(function (el) {{
  el.addEventListener('click', function (e) {{ e.stopPropagation(); }});
}});
</script>

</body>
</html>"""
