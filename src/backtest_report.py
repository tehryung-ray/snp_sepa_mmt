"""백테스트 결과 → GitHub Pages 리포트 HTML

정보 설계:
  - 한계(펀더멘털 제외 / 생존 편향)를 맨 위에 둔다. 숫자보다 먼저 읽혀야
    해석을 그르치지 않는다.
  - 자산곡선은 선그래프 1개 축. 전략 3종은 카테고리 색, 벤치마크(SPY)는
    회색 파선 — 벤치마크는 동급 시리즈가 아니라 기준선이므로 색을 쓰지 않는다.
  - 색은 눈으로 고르지 않고 검증했다. 실제 서피스(#131c2e) 기준
    validate_palette.js 전 항목 PASS (CVD ΔE 9.4 / 일반시야 ΔE 20.9).
  - 색만으로 식별하지 않도록 범례 + 선 끝 직접 라벨 + 표 뷰를 모두 제공한다.
"""

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

# 검증된 카테고리 색 (dark, surface #131c2e)
SERIES_COLORS = {3: "#3987e5", 5: "#d95926", 10: "#199e70"}
BENCH_COLOR = "#8b98ad"

_CSS = """
:root{
  --bg:#0b1220; --panel:#131c2e; --panel2:#1a2438; --line:#26324a;
  --ink:#e6ecf7; --ink2:#94a3b8; --ink3:#64748b;
  --accent:#f5a524; --good:#34d399; --warn:#fbbf24; --bad:#f87171;
  --grid:#1e2a42; --axis:#33415c;
}
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,'Apple SD Gothic Neo',
    'Malgun Gothic',sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.55;font-size:15px;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1020px;margin:0 auto;padding:0 16px}
.num{font-variant-numeric:tabular-nums}

header{background:linear-gradient(160deg,#16203a,#0e1728);
  border-bottom:1px solid var(--line);padding:30px 16px 26px}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin-bottom:8px}
h1{font-size:clamp(21px,4.4vw,29px);font-weight:800;letter-spacing:-.02em;text-wrap:balance}
.sub{margin-top:7px;font-size:13px;color:var(--ink2)}
.sub b{color:var(--ink);font-weight:600}
.back{display:inline-block;margin-top:14px;font-size:12.5px;color:var(--ink2);
  text-decoration:none;border-bottom:1px dashed #46587a}
.back:hover{color:var(--accent);border-bottom-color:var(--accent)}

/* 한계 — 숫자보다 먼저 */
.caveat{background:#2a1c14;border:1px solid #5a3a1e;border-radius:11px;
  padding:15px 17px;margin:22px 0}
.caveat h2{font-size:14px;font-weight:800;color:#fcd34d;margin-bottom:9px}
.caveat ul{list-style:none;font-size:13px;color:#e8d5b0}
.caveat li{padding:3px 0 3px 15px;position:relative}
.caveat li:before{content:'';position:absolute;left:3px;top:12px;width:4px;height:4px;
  border-radius:50%;background:#c9973f}
.caveat b{color:#fcd34d}

.sec{margin:32px 0}
.sec h2{font-size:17px;font-weight:800;margin-bottom:4px}
.sec-note{font-size:12.5px;color:var(--ink2);margin-bottom:14px}

/* 비교 표 */
.tbl{width:100%;border-collapse:collapse;background:var(--panel);
  border:1px solid var(--line);border-radius:11px;overflow:hidden}
.tbl th,.tbl td{padding:11px 13px;text-align:right;font-size:13.5px;
  border-bottom:1px solid var(--line)}
.tbl th{background:#0f1829;color:var(--ink3);font-size:10.5px;font-weight:700;
  letter-spacing:.07em;text-transform:uppercase}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl tr:last-child td{border-bottom:none}
.tbl tr.bench td{background:#0f1829;color:var(--ink2)}
/* 변형 3종 중 CAGR 최고 — 중립색으로만 표시한다. 셋 다 벤치마크에 질 수
   있으므로 초록(=좋음)으로 칠하면 결과를 오독하게 만든다. */
.tbl tr.best td{background:var(--panel2)}
.swatch{display:inline-block;width:10px;height:10px;border-radius:2px;
  margin-right:7px;vertical-align:middle}
.pos{color:var(--good)} .neg{color:var(--bad)}

/* 차트 */
.chartbox{background:var(--panel);border:1px solid var(--line);border-radius:11px;
  padding:16px 16px 10px;position:relative}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px;font-size:12.5px}
.legend span{display:flex;align-items:center;gap:6px;color:var(--ink2)}
.legend i{width:14px;height:3px;border-radius:2px;display:block}
svg.chart{width:100%;height:auto;display:block;overflow:visible}
.tip{position:absolute;pointer-events:none;background:#0a1120;border:1px solid var(--axis);
  border-radius:8px;padding:8px 10px;font-size:12px;opacity:0;transition:opacity .12s;
  box-shadow:0 6px 20px rgba(0,0,0,.5);white-space:nowrap;z-index:5}
.tip .d{color:var(--ink3);font-size:10.5px;margin-bottom:4px}
.tip .r{display:flex;align-items:center;gap:6px;margin-top:2px}
.tip .r i{width:9px;height:3px;border-radius:2px}
.tip .r b{margin-left:auto;padding-left:12px;font-variant-numeric:tabular-nums}

footer{margin-top:44px;padding:24px 16px 34px;border-top:1px solid var(--line);
  background:#0a101c;font-size:12px;color:var(--ink3)}
footer p{margin-bottom:5px}
footer b{color:var(--ink2)}

@media (max-width:700px){
  .tbl th,.tbl td{padding:9px 8px;font-size:12.5px}
  .scroll{overflow-x:auto}
}
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _sign(v, digits=2, suffix="%"):
    """부호에 따라 색 클래스를 붙인 숫자."""
    if v is None:
        return "—"
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    return f'<span class="{cls} num">{v:+,.{digits}f}{suffix}</span>'


def _build_chart(curves: Dict[str, pd.Series], width=940, height=340) -> str:
    """자산곡선 선그래프.

    - 축은 하나(자산가치). 이중축은 쓰지 않는다.
    - 선 2px, 그리드는 후퇴색, 선 끝에 직접 라벨.
    - 주 단위로 샘플링해 경로 데이터를 줄인다(6년 일봉 → 약 310점).
    """
    # y축 눈금은 왼쪽, 시리즈 직접 라벨은 오른쪽 — 같은 여백을 쓰면 겹친다.
    pad_l, pad_r, pad_t, pad_b = 46, 64, 14, 26
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b

    # 주 단위 샘플링 + 마지막 점 보존
    sampled = {}
    for k, s in curves.items():
        w = s.resample("W").last().dropna()
        if len(w) and w.index[-1] != s.index[-1]:
            w = pd.concat([w, s.iloc[[-1]]])
        sampled[k] = w

    all_vals = pd.concat(sampled.values())
    vmin, vmax = float(all_vals.min()), float(all_vals.max())
    span = vmax - vmin or 1
    vmin -= span * 0.06
    vmax += span * 0.06

    idx = list(sampled.values())[0].index
    t0, t1 = idx[0].value, idx[-1].value
    tspan = (t1 - t0) or 1

    def X(ts):
        return pad_l + (ts.value - t0) / tspan * iw

    def Y(v):
        return pad_t + (vmax - v) / (vmax - vmin) * ih

    # ── 그리드 + y축 눈금 ────────────────────────────────────────
    # 1/2/5 × 10ⁿ 중 눈금이 5개 안팎이 되는 간격을 고른다.
    parts = []
    import math
    raw = (vmax - vmin) / 5
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = next((m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag), 10 * mag)

    ticks, t = [], math.ceil(vmin / step) * step
    while t < vmax and len(ticks) < 10:
        ticks.append(t)
        t += step
    for tv in ticks:
        y = Y(tv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l+iw}" y2="{y:.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" fill="var(--ink3)" '
                     f'font-size="10.5" text-anchor="end" '
                     f'font-variant-numeric="tabular-nums">{tv/1000:,.0f}k</text>')

    # ── x축 연도 눈금 ────────────────────────────────────────────
    years = sorted({d.year for d in idx})
    for yr in years:
        first = next((d for d in idx if d.year == yr), None)
        if first is None:
            continue
        x = X(first)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t+ih}" '
                     f'stroke="var(--grid)" stroke-width="1" stroke-dasharray="2 3"/>')
        parts.append(f'<text x="{x:.1f}" y="{pad_t+ih+17}" fill="var(--ink3)" '
                     f'font-size="10.5" text-anchor="middle">{yr}</text>')

    # ── 선 ──────────────────────────────────────────────────────
    order = [k for k in curves if k != "SPY"] + (["SPY"] if "SPY" in curves else [])
    for key in order:
        s = sampled[key]
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(ts):.1f},{Y(v):.1f}"
                     for i, (ts, v) in enumerate(s.items()))
        if key == "SPY":
            parts.append(f'<path d="{d}" fill="none" stroke="{BENCH_COLOR}" '
                         f'stroke-width="2" stroke-dasharray="5 4" '
                         f'stroke-linejoin="round" stroke-linecap="round"/>')
        else:
            color = SERIES_COLORS[int(key)]
            parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" '
                         f'stroke-linejoin="round" stroke-linecap="round"/>')

    # ── 선 끝 직접 라벨 (색만으로 식별하지 않게) ────────────────
    ends = sorted(((k, sampled[k].iloc[-1]) for k in order), key=lambda x: -x[1])
    last_y = -99
    for key, val in ends:
        y = Y(val)
        if y - last_y < 13:      # 라벨 충돌 회피
            y = last_y + 13
        last_y = y
        color = BENCH_COLOR if key == "SPY" else SERIES_COLORS[int(key)]
        label = "SPY" if key == "SPY" else f"{key}종목"
        parts.append(f'<text x="{pad_l+iw+7}" y="{y+4:.1f}" fill="{color}" '
                     f'font-size="11" font-weight="700">{label}</text>')

    svg = (f'<svg class="chart" viewBox="0 0 {width} {height}" '
           f'preserveAspectRatio="xMidYMid meet" role="img" '
           f'aria-label="전략별 자산곡선과 SPY 비교">'
           + "".join(parts) +
           f'<rect id="hit" x="{pad_l}" y="{pad_t}" width="{iw}" height="{ih}" fill="transparent"/>'
           f'<line id="cross" x1="0" y1="{pad_t}" x2="0" y2="{pad_t+ih}" '
           f'stroke="var(--axis)" stroke-width="1" opacity="0"/>'
           '</svg>')

    # 호버용 데이터
    hover = {
        "x0": pad_l, "iw": iw, "w": width,
        "dates": [d.strftime("%Y-%m-%d") for d in sampled[order[0]].index],
        "series": [{"key": ("SPY" if k == "SPY" else f"{k}종목"),
                    "color": (BENCH_COLOR if k == "SPY" else SERIES_COLORS[int(k)]),
                    "vals": [round(float(v)) for v in sampled[k].values]}
                   for k in order],
    }
    return svg, hover


def build_backtest_html(summary: Dict, curves: Dict[str, pd.Series]) -> str:
    svg, hover = _build_chart(curves)

    p = summary["period"]
    prm = summary["params"]
    by = summary["by_positions"]
    keys = sorted(by, key=lambda x: int(x))
    bench = by[keys[0]]["benchmark"]

    best = max(keys, key=lambda k: by[k]["strategy"]["cagr"])

    # ── 비교 표 ─────────────────────────────────────────────────
    rows = []
    for k in keys:
        m = by[k]
        s = m["strategy"]
        cls = " class=\"best\"" if k == best else ""
        rows.append(f"""<tr{cls}>
  <td><span class="swatch" style="background:{SERIES_COLORS[int(k)]}"></span><b>{k}종목</b></td>
  <td>{_sign(s['total_return'])}</td>
  <td>{_sign(s['cagr'])}</td>
  <td class="num neg">{s['mdd']:.1f}%</td>
  <td class="num">{s['sharpe']:.2f}</td>
  <td class="num">{s['sortino']:.2f}</td>
  <td>{_sign(m['alpha'])}</td>
  <td class="num">{m['positions']}</td>
  <td class="num">{m['win_rate']:.1f}%</td>
  <td class="num">{m['exposure']:.0f}%</td>
</tr>""")

    rows.append(f"""<tr class="bench">
  <td><span class="swatch" style="background:{BENCH_COLOR}"></span><b>SPY 매수보유</b></td>
  <td>{_sign(bench['total_return'])}</td>
  <td>{_sign(bench['cagr'])}</td>
  <td class="num neg">{bench['mdd']:.1f}%</td>
  <td class="num">{bench['sharpe']:.2f}</td>
  <td class="num">{bench['sortino']:.2f}</td>
  <td class="num">—</td><td class="num">—</td><td class="num">—</td>
  <td class="num">100%</td>
</tr>""")

    # ── 매매 통계 표 ────────────────────────────────────────────
    trows = []
    for k in keys:
        m = by[k]
        pf = m["profit_factor"]
        trows.append(f"""<tr>
  <td><span class="swatch" style="background:{SERIES_COLORS[int(k)]}"></span><b>{k}종목</b></td>
  <td class="num">{m['positions']}</td>
  <td class="num">{m['win_rate']:.1f}%</td>
  <td class="num pos">{m['avg_win']:+.1f}%</td>
  <td class="num neg">{m['avg_loss']:+.1f}%</td>
  <td class="num">{pf if pf is not None else '—'}</td>
  <td>{_sign(m['expectancy'], 2)}</td>
  <td class="num">{m['avg_days']:.0f}일</td>
</tr>""")

    caveats = "".join(f"<li>{_esc(c)}</li>" for c in summary["caveats"])
    w = prm["momentum_weights"]
    weight_str = " + ".join(f"{v}×{k}개월" for k, v in sorted(w.items(), key=lambda x: int(x[0])))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    legend = "".join(
        f'<span><i style="background:{SERIES_COLORS[int(k)]}"></i>{k}종목</span>'
        for k in keys
    ) + f'<span><i style="background:{BENCH_COLOR}"></i>SPY 매수보유</span>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>백테스트 | 모멘텀 × SEPA</title>
<meta name="description" content="가중모멘텀 × SEPA 전략의 {p['years']}년 백테스트 결과">
<style>{_CSS}</style>
</head>
<body>

<header>
  <div class="wrap">
    <div class="eyebrow">Backtest</div>
    <h1>가중모멘텀 × SEPA 전략 {p['years']}년 검증</h1>
    <p class="sub"><b>{_esc(p['start'])}</b> ~ <b>{_esc(p['end'])}</b>
      · 유니버스 <b>{summary['universe_size']}종목</b>
      · 초기자본 <b>${prm['initial_capital']:,.0f}</b></p>
    <a class="back" href="./">← 일일 스크리너로 돌아가기</a>
  </div>
</header>

<div class="wrap">

  <div class="caveat">
    <h2>⚠ 결과를 읽기 전에 — 이 백테스트의 한계</h2>
    <ul>{caveats}</ul>
  </div>

  <section class="sec">
    <h2>자산곡선</h2>
    <p class="sec-note">최대 보유 종목 수를 3·5·10으로 바꿔가며 비교. 회색 파선이 SPY 매수보유입니다.</p>
    <div class="chartbox">
      <div class="legend">{legend}</div>
      {svg}
      <div class="tip" id="tip"></div>
    </div>
  </section>

  <section class="sec">
    <h2>성과 비교</h2>
    <p class="sec-note">MDD는 최대 낙폭, 노출도는 평균 보유 비중입니다.</p>
    <div class="scroll">
    <table class="tbl">
      <tr>
        <th>구성</th><th>총수익</th><th>CAGR</th><th>MDD</th><th>Sharpe</th>
        <th>Sortino</th><th>알파</th><th>매매</th><th>승률</th><th>노출도</th>
      </tr>
      {''.join(rows)}
    </table>
    </div>
  </section>

  <section class="sec">
    <h2>매매 통계</h2>
    <p class="sec-note">포지션(라운드트립) 기준입니다. 부분익절은 별도 건으로 세지 않고 수량가중 평균으로 합산했습니다.</p>
    <div class="scroll">
    <table class="tbl">
      <tr>
        <th>구성</th><th>포지션</th><th>승률</th><th>평균이익</th><th>평균손실</th>
        <th>손익비(PF)</th><th>기대값</th><th>평균보유</th>
      </tr>
      {''.join(trows)}
    </table>
    </div>
  </section>

</div>

<footer>
  <div class="wrap">
    <p><b>진입</b> — 매주 월요일 종가로 모멘텀 상위 {prm['top_n']}개를 SEPA 채점,
       Phase 2 · 트렌드 템플릿 {prm['template_min']}/8 이상 · SEPA {prm['sepa_threshold']}점 이상을
       모두 만족한 종목을 SEPA 점수 순으로 편입. 체결은 다음 거래일 시가.</p>
    <p><b>청산</b> — 1차 익절가((매수가+익절가)÷2) 도달 시 50% 매도 후 손절가를 매수가로 상향.
       나머지는 익절가 도달 시 익절, 또는 상향된 손절가 도달 시 청산.</p>
    <p><b>모멘텀</b> — {_esc(weight_str)} 수익률의 가중합.</p>
    <p style="margin-top:12px">생성 {now} · 데이터 yfinance / Wikipedia</p>
    <p style="color:#4a5568">본 페이지는 정보 제공 목적이며 투자 자문이 아닙니다.
       백테스트 결과는 과거 데이터에 대한 시뮬레이션이며 미래 수익을 보장하지 않습니다.</p>
  </div>
</footer>

<script>
(function () {{
  var H = {json.dumps(hover, ensure_ascii=False)};
  var svg = document.querySelector('svg.chart');
  var hit = document.getElementById('hit');
  var cross = document.getElementById('cross');
  var tip = document.getElementById('tip');
  if (!svg || !hit) return;
  var box = svg.parentElement;

  function show(e) {{
    var r = svg.getBoundingClientRect();
    var vx = (e.clientX - r.left) / r.width * H.w;          // viewBox 좌표로 환산
    var f = (vx - H.x0) / H.iw;
    var i = Math.round(f * (H.dates.length - 1));
    if (i < 0) i = 0;
    if (i > H.dates.length - 1) i = H.dates.length - 1;

    var sx = H.x0 + (i / (H.dates.length - 1)) * H.iw;
    cross.setAttribute('x1', sx); cross.setAttribute('x2', sx);
    cross.setAttribute('opacity', '1');

    var rows = H.series.map(function (s) {{
      return '<div class="r"><i style="background:' + s.color + '"></i>' + s.key +
             '<b>' + s.vals[i].toLocaleString() + '</b></div>';
    }}).join('');
    tip.innerHTML = '<div class="d">' + H.dates[i] + '</div>' + rows;
    tip.style.opacity = '1';

    var px = sx / H.w * r.width;
    var bw = box.getBoundingClientRect().width;
    var tw = tip.offsetWidth;
    tip.style.left = Math.max(4, Math.min(px + 14, bw - tw - 4)) + 'px';
    tip.style.top = '44px';
  }}

  hit.addEventListener('mousemove', show);
  hit.addEventListener('mouseleave', function () {{
    cross.setAttribute('opacity', '0');
    tip.style.opacity = '0';
  }});
}})();
</script>

</body>
</html>"""


def generate(backtest_dir: Path, out_path: Path) -> Path:
    """summary.json + equity_*.csv 를 읽어 리포트 HTML을 만든다."""
    summary = json.loads((backtest_dir / "summary.json").read_text(encoding="utf-8"))

    curves = {}
    for k in summary["by_positions"]:
        df = pd.read_csv(backtest_dir / f"equity_{k}.csv", index_col=0, parse_dates=True)
        curves[k] = df["equity"]
    bdf = pd.read_csv(backtest_dir / "equity_benchmark.csv", index_col=0, parse_dates=True)
    curves["SPY"] = bdf["equity"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_backtest_html(summary, curves), encoding="utf-8")
    return out_path
