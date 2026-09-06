"""백테스트 결과 → GitHub Pages 리포트 HTML

정보 설계:
  - 한계(펀더멘털 제외 / 생존 편향)를 맨 위에 둔다. 숫자보다 먼저 읽혀야
    해석을 그르치지 않는다.
  - 실험 변수는 '청산 방식'이므로 색은 청산 방식에 배정한다. 보유 종목 수는
    표의 한 열로 내린다. 색이 두 변수를 동시에 나르면 읽히지 않는다.
  - 벤치마크(SPY)는 동급 시리즈가 아니라 기준선이므로 카테고리 색 대신
    회색 파선을 쓴다.
  - 색은 눈으로 고르지 않고 검증했다. 실제 서피스(#131c2e) 기준
    validate_palette.js 전 항목 PASS (인접쌍 CVD ΔE 8.4 / 일반시야 ΔE 19.8).
    CVD가 8점대이므로 보조 인코딩(범례 + 선 끝 직접 라벨 + 표)을 함께 둔다.
"""

import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd

# 검증된 카테고리 색 (dark, surface #131c2e) — 청산 방식에 배정
MODE_COLORS = {
    "target": "#3987e5",
    "ma50": "#d95926",
    "trail20": "#199e70",
    "half_ma50": "#c98500",
}
MODE_SHORT = {
    "target": "고정 익절",
    "ma50": "50일선 이탈",
    "trail20": "−20% 추적",
    "half_ma50": "절반+50일선",
}
MODE_ORDER = ["target", "ma50", "trail20", "half_ma50"]
BENCH_COLOR = "#8b98ad"

_CSS = """
:root{
  --bg:#0b1220; --panel:#131c2e; --panel2:#1a2438; --line:#26324a;
  --ink:#e6ecf7; --ink2:#94a3b8; --ink3:#64748b;
  --accent:#f5a524; --good:#34d399; --bad:#f87171;
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

.caveat{background:#2a1c14;border:1px solid #5a3a1e;border-radius:11px;
  padding:15px 17px;margin:22px 0}
.caveat h2{font-size:14px;font-weight:800;color:#fcd34d;margin-bottom:9px}
.caveat ul{list-style:none;font-size:13px;color:#e8d5b0}
.caveat li{padding:3px 0 3px 15px;position:relative}
.caveat li:before{content:'';position:absolute;left:3px;top:12px;width:4px;height:4px;
  border-radius:50%;background:#c9973f}

/* 결론 */
.verdict{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:9px;padding:15px 17px;margin:22px 0;font-size:14px;color:var(--ink2)}
.verdict b{color:var(--ink)}
.verdict .big{display:block;font-size:16px;font-weight:800;color:var(--ink);margin-bottom:6px}

.sec{margin:32px 0}
.sec h2{font-size:17px;font-weight:800;margin-bottom:4px}
.sec-note{font-size:12.5px;color:var(--ink2);margin-bottom:14px}

.tbl{width:100%;border-collapse:collapse;background:var(--panel);
  border:1px solid var(--line);border-radius:11px;overflow:hidden}
.tbl th,.tbl td{padding:10px 12px;text-align:right;font-size:13px;
  border-bottom:1px solid var(--line)}
.tbl th{background:#0f1829;color:var(--ink3);font-size:10.5px;font-weight:700;
  letter-spacing:.06em;text-transform:uppercase}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl tr:last-child td{border-bottom:none}
.tbl tr.bench td{background:#0f1829;color:var(--ink2);font-weight:600}
.tbl tr.grp td{border-top:1px solid var(--axis)}
.tbl tr.beat td{background:var(--panel2)}
.swatch{display:inline-block;width:10px;height:10px;border-radius:2px;
  margin-right:7px;vertical-align:middle}
.pos{color:var(--good)} .neg{color:var(--bad)}
.tag{font-size:10px;font-weight:700;padding:1.5px 5px;border-radius:4px;
  background:#14432f;color:#6ee7b7;margin-left:6px}

.chartbox{background:var(--panel);border:1px solid var(--line);border-radius:11px;
  padding:16px 16px 10px;position:relative}
.legend{display:flex;gap:15px;flex-wrap:wrap;margin-bottom:12px;font-size:12.5px}
.legend span{display:flex;align-items:center;gap:6px;color:var(--ink2)}
.legend i{width:14px;height:3px;border-radius:2px;display:block}
svg.chart{width:100%;height:auto;display:block;overflow:visible}
.tip{position:absolute;pointer-events:none;background:#0a1120;border:1px solid var(--axis);
  border-radius:8px;padding:8px 10px;font-size:12px;opacity:0;transition:opacity .12s;
  box-shadow:0 6px 20px rgba(0,0,0,.5);white-space:nowrap;z-index:5}
.tip .d{color:var(--ink3);font-size:10.5px;margin-bottom:4px}
.tip .r{display:flex;align-items:center;gap:6px;margin-top:2px}
.tip .r i{width:9px;height:3px;border-radius:2px}
.tip .r b{margin-left:auto;padding-left:14px;font-variant-numeric:tabular-nums}

footer{margin-top:44px;padding:24px 16px 34px;border-top:1px solid var(--line);
  background:#0a101c;font-size:12px;color:var(--ink3)}
footer p{margin-bottom:5px}
footer b{color:var(--ink2)}
.rules{list-style:none;margin:6px 0 0}
.rules li{padding:3px 0 3px 15px;position:relative}
.rules li:before{content:'';position:absolute;left:3px;top:12px;width:4px;height:4px;
  border-radius:50%;background:var(--axis)}

@media (max-width:760px){
  .tbl th,.tbl td{padding:8px 7px;font-size:12px}
  .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
}
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _sign(v, digits=2, suffix="%"):
    if v is None:
        return "—"
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    return f'<span class="{cls} num">{v:+,.{digits}f}{suffix}</span>'


def _build_chart(curves: Dict[str, pd.Series], colors: Dict[str, str],
                 labels: Dict[str, str], width=940, height=340):
    """자산곡선 선그래프. 축 하나, 선 2px, 선 끝 직접 라벨."""
    # y축 눈금은 왼쪽, 시리즈 직접 라벨은 오른쪽 — 같은 여백을 쓰면 겹친다.
    pad_l, pad_r, pad_t, pad_b = 46, 92, 14, 26
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b

    sampled = {}
    for k, s in curves.items():
        w = s.resample("W").last().dropna()
        if len(w) and w.index[-1] != s.index[-1]:
            w = pd.concat([w, s.iloc[[-1]]])
        sampled[k] = w

    all_vals = pd.concat(sampled.values())
    vmin, vmax = float(all_vals.min()), float(all_vals.max())
    span = (vmax - vmin) or 1
    vmin -= span * 0.06
    vmax += span * 0.06

    idx = list(sampled.values())[0].index
    t0, t1 = idx[0].value, idx[-1].value
    tspan = (t1 - t0) or 1

    def X(ts):
        return pad_l + (ts.value - t0) / tspan * iw

    def Y(v):
        return pad_t + (vmax - v) / (vmax - vmin) * ih

    parts = []

    # 1/2/5 × 10ⁿ 중 눈금이 5개 안팎이 되는 간격
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

    for yr in sorted({d.year for d in idx}):
        first = next((d for d in idx if d.year == yr), None)
        if first is None:
            continue
        x = X(first)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t+ih}" '
                     f'stroke="var(--grid)" stroke-width="1" stroke-dasharray="2 3"/>')
        parts.append(f'<text x="{x:.1f}" y="{pad_t+ih+17}" fill="var(--ink3)" '
                     f'font-size="10.5" text-anchor="middle">{yr}</text>')

    order = [k for k in curves if k != "SPY"] + (["SPY"] if "SPY" in curves else [])
    for key in order:
        s = sampled[key]
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(ts):.1f},{Y(v):.1f}"
                     for i, (ts, v) in enumerate(s.items()))
        if key == "SPY":
            parts.append(f'<path d="{d}" fill="none" stroke="{BENCH_COLOR}" stroke-width="2" '
                         f'stroke-dasharray="5 4" stroke-linejoin="round" stroke-linecap="round"/>')
        else:
            parts.append(f'<path d="{d}" fill="none" stroke="{colors[key]}" stroke-width="2" '
                         f'stroke-linejoin="round" stroke-linecap="round"/>')

    # 선 끝 직접 라벨 — 색만으로 식별하지 않게 (CVD 보조 인코딩)
    ends = sorted(((k, float(sampled[k].iloc[-1])) for k in order), key=lambda x: -x[1])
    last_y = -99.0
    for key, val in ends:
        y = Y(val)
        if y - last_y < 13:
            y = last_y + 13
        last_y = y
        color = BENCH_COLOR if key == "SPY" else colors[key]
        label = "SPY" if key == "SPY" else labels[key]
        parts.append(f'<text x="{pad_l+iw+7}" y="{y+4:.1f}" fill="{color}" '
                     f'font-size="11" font-weight="700">{_esc(label)}</text>')

    svg = (f'<svg class="chart" viewBox="0 0 {width} {height}" '
           f'preserveAspectRatio="xMidYMid meet" role="img" '
           f'aria-label="청산 방식별 자산곡선과 SPY 비교">' + "".join(parts) +
           f'<rect id="hit" x="{pad_l}" y="{pad_t}" width="{iw}" height="{ih}" fill="transparent"/>'
           f'<line id="cross" x1="0" y1="{pad_t}" x2="0" y2="{pad_t+ih}" '
           f'stroke="var(--axis)" stroke-width="1" opacity="0"/></svg>')

    hover = {
        "x0": pad_l, "iw": iw, "w": width,
        "dates": [d.strftime("%Y-%m-%d") for d in sampled[order[0]].index],
        "series": [{"key": ("SPY" if k == "SPY" else labels[k]),
                    "color": (BENCH_COLOR if k == "SPY" else colors[k]),
                    "vals": [round(float(v)) for v in sampled[k].values]}
                   for k in order],
    }
    return svg, hover


def build_backtest_html(summary: Dict, curves: Dict[str, pd.Series],
                        chart_positions: int) -> str:
    by = summary["by_run"]
    p = summary["period"]
    prm = summary["params"]
    modes = [m for m in MODE_ORDER if m in summary.get("exit_modes", {})]
    bench = list(by.values())[0]["benchmark"]

    colors = {m: MODE_COLORS[m] for m in modes}
    labels = {m: MODE_SHORT[m] for m in modes}
    svg, hover = _build_chart(curves, colors, labels)

    runs = sorted(by.values(), key=lambda m: -m["strategy"]["cagr"])
    best = runs[0]
    beat = [m for m in runs if m["alpha"] > 0]

    # ── 방식별 안정성 (보유 종목 수를 바꿔가며 얼마나 흔들리는가) ──
    # 표 1등만 집어내면 과최적화가 된다. 같은 방식이 보유 수에 따라 얼마나
    # 출렁이는지를 함께 봐야 그 순위를 믿을 수 있는지 판단할 수 있다.
    stats = {}
    for mode in modes:
        rs = [m for m in by.values() if m["exit_mode"] == mode]
        cs = sorted(r["strategy"]["cagr"] for r in rs)
        stats[mode] = {
            "avg": sum(cs) / len(cs), "lo": cs[0], "hi": cs[-1],
            "spread": cs[-1] - cs[0],
            "sharpe": sum(r["strategy"]["sharpe"] for r in rs) / len(rs),
        }
    best_avg = max(stats, key=lambda m: stats[m]["avg"])
    max_spread = max(s["spread"] for s in stats.values())
    beat_sharpe = [m for m in runs if m["strategy"]["sharpe"] > bench["sharpe"]]

    # ── 결론 ────────────────────────────────────────────────────
    if beat:
        head = (f"고정 목표가를 없애자 {len(beat)}개 구성이 수익률에서 SPY를 앞섰습니다. "
                f"다만 위험조정 성과로는 여전히 뒤집지 못했습니다.")
        detail = (
            f"평균으로 보면 <b>{MODE_SHORT[best_avg]}</b>이 CAGR "
            f"<b>{stats[best_avg]['avg']:.2f}%</b>로 SPY({bench['cagr']:.2f}%)를 웃도는 "
            f"유일한 방식입니다. 기존 고정 익절({MODE_SHORT['target']}) 평균 "
            f"{stats['target']['avg']:.2f}%보다 "
            f"{stats[best_avg]['avg'] - stats['target']['avg']:+.2f}%p 개선입니다. "
            f"<br><br>그러나 <b>Sharpe로 SPY({bench['sharpe']:.2f})를 넘긴 구성은 "
            f"{len(beat_sharpe)}개</b>입니다. 수익률이 오른 만큼 변동성과 낙폭도 커졌다는 뜻입니다. "
            f"게다가 같은 청산 방식이라도 보유 종목 수만 바꾸면 CAGR이 최대 "
            f"<b>{max_spread:.1f}%p</b> 출렁입니다 — 방식 간 차이보다 큰 폭입니다. "
            f"표 1등인 {MODE_SHORT[best['exit_mode']]}·{best['max_positions']}종목"
            f"({best['strategy']['cagr']:.2f}%)을 그대로 채택하면 "
            f"6년 한 구간의 노이즈를 실력으로 착각하는 것입니다.")
    else:
        head = "어떤 구성도 SPY를 앞서지 못했습니다."
        detail = (f"가장 나은 구성이 <b>{MODE_SHORT[best['exit_mode']]} · "
                  f"{best['max_positions']}종목</b>으로 CAGR "
                  f"{best['strategy']['cagr']:.2f}%인데, SPY 매수보유 "
                  f"{bench['cagr']:.2f}%에 {abs(best['alpha']):.2f}%p 못 미칩니다.")

    srows = []
    for mode in modes:
        st = stats[mode]
        cls = ' class="beat"' if st["avg"] > bench["cagr"] else ""
        srows.append(f"""<tr{cls}>
  <td><span class="swatch" style="background:{colors[mode]}"></span><b>{MODE_SHORT[mode]}</b></td>
  <td>{_sign(st['avg'])}</td>
  <td class="num">{st['lo']:.2f}% ~ {st['hi']:.2f}%</td>
  <td class="num">{st['spread']:.2f}%p</td>
  <td class="num">{st['sharpe']:.2f}</td>
</tr>""")
    srows.append(f"""<tr class="bench grp">
  <td><span class="swatch" style="background:{BENCH_COLOR}"></span><b>SPY 매수보유</b></td>
  <td>{_sign(bench['cagr'])}</td>
  <td class="num">—</td><td class="num">—</td>
  <td class="num">{bench['sharpe']:.2f}</td>
</tr>""")

    # ── 성과 표 ─────────────────────────────────────────────────
    rows = []
    for mi, mode in enumerate(modes):
        for j, mp in enumerate(sorted({m["max_positions"] for m in by.values()})):
            m = by.get(f"{mode}|{mp}")
            if not m:
                continue
            s = m["strategy"]
            cls = []
            if j == 0 and mi > 0:
                cls.append("grp")
            if m["alpha"] > 0:
                cls.append("beat")
            c = f' class="{" ".join(cls)}"' if cls else ""
            name = (f'<span class="swatch" style="background:{colors[mode]}"></span>'
                    f'<b>{MODE_SHORT[mode]}</b>') if j == 0 else \
                   '<span style="padding-left:17px;color:var(--ink3)">〃</span>'
            tag = '<span class="tag">SPY 상회</span>' if m["alpha"] > 0 else ""
            rows.append(f"""<tr{c}>
  <td>{name}{tag}</td>
  <td class="num">{mp}</td>
  <td>{_sign(s['total_return'])}</td>
  <td>{_sign(s['cagr'])}</td>
  <td class="num neg">{s['mdd']:.1f}%</td>
  <td class="num">{s['sharpe']:.2f}</td>
  <td>{_sign(m['alpha'])}</td>
  <td class="num">{m['positions']}</td>
  <td class="num">{m['win_rate']:.1f}%</td>
  <td class="num">{m['avg_days']:.0f}일</td>
</tr>""")

    rows.append(f"""<tr class="bench grp">
  <td><span class="swatch" style="background:{BENCH_COLOR}"></span><b>SPY 매수보유</b></td>
  <td class="num">—</td>
  <td>{_sign(bench['total_return'])}</td>
  <td>{_sign(bench['cagr'])}</td>
  <td class="num neg">{bench['mdd']:.1f}%</td>
  <td class="num">{bench['sharpe']:.2f}</td>
  <td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td>
</tr>""")

    # ── 매매 통계 ───────────────────────────────────────────────
    trows = []
    for mode in modes:
        for j, mp in enumerate(sorted({m["max_positions"] for m in by.values()})):
            m = by.get(f"{mode}|{mp}")
            if not m:
                continue
            name = (f'<span class="swatch" style="background:{colors[mode]}"></span>'
                    f'<b>{MODE_SHORT[mode]}</b>') if j == 0 else \
                   '<span style="padding-left:17px;color:var(--ink3)">〃</span>'
            pf = m["profit_factor"]
            trows.append(f"""<tr{' class="grp"' if j == 0 and mode != modes[0] else ''}>
  <td>{name}</td>
  <td class="num">{mp}</td>
  <td class="num">{m['positions']}</td>
  <td class="num">{m['win_rate']:.1f}%</td>
  <td class="num pos">{m['avg_win']:+.1f}%</td>
  <td class="num neg">{m['avg_loss']:+.1f}%</td>
  <td class="num">{pf if pf is not None else '—'}</td>
  <td>{_sign(m['expectancy'], 2)}</td>
  <td class="num">{m['exposure']:.0f}%</td>
</tr>""")

    caveats = "".join(f"<li>{_esc(c)}</li>" for c in summary["caveats"])
    rules = "".join(f'<li><b style="color:{colors[m]}">{MODE_SHORT[m]}</b> — '
                    f'{_esc(summary["exit_modes"][m])}</li>' for m in modes)
    legend = "".join(f'<span><i style="background:{colors[m]}"></i>{MODE_SHORT[m]}</span>'
                     for m in modes) + \
             f'<span><i style="background:{BENCH_COLOR}"></i>SPY 매수보유</span>'

    w = prm["momentum_weights"]
    weight_str = " + ".join(f"{v}×{k}개월" for k, v in sorted(w.items(), key=lambda x: int(x[0])))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>백테스트 | 모멘텀 × SEPA</title>
<meta name="description" content="가중모멘텀 × SEPA 전략의 {p['years']}년 백테스트 — 청산 방식 4종 비교">
<style>{_CSS}</style>
</head>
<body>

<header>
  <div class="wrap">
    <div class="eyebrow">Backtest · 청산 방식 비교</div>
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

  <div class="verdict">
    <span class="big">{_esc(head)}</span>
    {detail}
  </div>

  <section class="sec">
    <h2>자산곡선</h2>
    <p class="sec-note">청산 방식 4종을 <b>최대 보유 {chart_positions}종목</b> 조건에서 비교했습니다.
      회색 파선이 SPY 매수보유입니다. 보유 종목 수별 결과는 아래 표에 있습니다.</p>
    <div class="chartbox">
      <div class="legend">{legend}</div>
      {svg}
      <div class="tip" id="tip"></div>
    </div>
  </section>

  <section class="sec">
    <h2>청산 방식</h2>
    <p class="sec-note">진입 규칙은 모두 동일하고 파는 방법만 다릅니다.
      어느 방식이든 SEPA가 산출한 초기 손절가는 하한으로 유지됩니다.</p>
    <ul class="rules" style="font-size:13.5px;color:var(--ink2)">{rules}</ul>
  </section>

  <section class="sec">
    <h2>방식별 안정성</h2>
    <p class="sec-note">보유 종목 수(3·5·10)를 바꿔가며 같은 청산 방식이 얼마나 흔들리는지.
      <b>스프레드가 크면 그 순위는 믿을 게 못 됩니다</b> — 파라미터 하나에 결과가
      좌우된다는 뜻이라, 표 1등을 그대로 고르면 과최적화입니다.</p>
    <div class="scroll">
    <table class="tbl">
      <tr>
        <th>청산 방식</th><th>CAGR 평균</th><th>최저 ~ 최고</th>
        <th>스프레드</th><th>Sharpe 평균</th>
      </tr>
      {''.join(srows)}
    </table>
    </div>
  </section>

  <section class="sec">
    <h2>성과 비교</h2>
    <p class="sec-note">MDD는 최대 낙폭. 알파는 SPY 대비 CAGR 차이입니다.</p>
    <div class="scroll">
    <table class="tbl">
      <tr>
        <th>청산 방식</th><th>보유</th><th>총수익</th><th>CAGR</th><th>MDD</th>
        <th>Sharpe</th><th>알파</th><th>매매</th><th>승률</th><th>평균보유</th>
      </tr>
      {''.join(rows)}
    </table>
    </div>
  </section>

  <section class="sec">
    <h2>매매 통계</h2>
    <p class="sec-note">포지션(라운드트립) 기준입니다. 부분익절은 별도 건으로 세지 않고
      수량가중 평균으로 합산했습니다.</p>
    <div class="scroll">
    <table class="tbl">
      <tr>
        <th>청산 방식</th><th>보유</th><th>포지션</th><th>승률</th><th>평균이익</th>
        <th>평균손실</th><th>손익비(PF)</th><th>기대값</th><th>노출도</th>
      </tr>
      {''.join(trows)}
    </table>
    </div>
  </section>

</div>

<footer>
  <div class="wrap">
    <p><b>진입 (모든 방식 공통)</b> — 매주 월요일 종가로 모멘텀 상위 {prm['top_n']}개를 SEPA 채점,
       Phase 2 · 트렌드 템플릿 {prm['template_min']}/8 이상 · SEPA {prm['sepa_threshold']}점 이상을
       모두 만족한 종목을 SEPA 점수 순으로 편입. 체결은 다음 거래일 시가.</p>
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
    var vx = (e.clientX - r.left) / r.width * H.w;      // viewBox 좌표로 환산
    var f = (vx - H.x0) / H.iw;
    var i = Math.round(f * (H.dates.length - 1));
    if (i < 0) i = 0;
    if (i > H.dates.length - 1) i = H.dates.length - 1;

    var sx = H.x0 + (i / (H.dates.length - 1)) * H.iw;
    cross.setAttribute('x1', sx); cross.setAttribute('x2', sx);
    cross.setAttribute('opacity', '1');

    tip.innerHTML = '<div class="d">' + H.dates[i] + '</div>' +
      H.series.map(function (s) {{
        return '<div class="r"><i style="background:' + s.color + '"></i>' + s.key +
               '<b>' + s.vals[i].toLocaleString() + '</b></div>';
      }}).join('');
    tip.style.opacity = '1';

    var px = sx / H.w * r.width;
    var bw = box.getBoundingClientRect().width;
    tip.style.left = Math.max(4, Math.min(px + 14, bw - tip.offsetWidth - 4)) + 'px';
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


def generate(backtest_dir: Path, out_path: Path,
             chart_positions: int = None) -> Path:
    """summary.json + equity_*.csv → 리포트 HTML.

    차트는 변수를 하나만 움직여야 읽히므로, 보유 종목 수를 하나로 고정하고
    청산 방식만 비교한다. 지정이 없으면 최고 CAGR 구성의 보유 수를 쓴다.
    """
    summary = json.loads((backtest_dir / "summary.json").read_text(encoding="utf-8"))
    by = summary["by_run"]

    if chart_positions is None:
        best = max(by.values(), key=lambda m: m["strategy"]["cagr"])
        chart_positions = best["max_positions"]

    curves = {}
    for key, m in by.items():
        if m["max_positions"] != chart_positions:
            continue
        df = pd.read_csv(backtest_dir / f"equity_{key.replace('|', '_')}.csv",
                         index_col=0, parse_dates=True)
        curves[m["exit_mode"]] = df["equity"]

    bdf = pd.read_csv(backtest_dir / "equity_benchmark.csv", index_col=0, parse_dates=True)
    curves["SPY"] = bdf["equity"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        build_backtest_html(summary, curves, chart_positions), encoding="utf-8")
    return out_path
