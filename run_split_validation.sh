#!/usr/bin/env bash
# 구간 분할 검증 — 같은 전략을 전반/후반으로 나눠 우위가 유지되는지 본다.
#
# 6년 한 구간의 1등은 노이즈일 수 있다. 두 구간 모두에서 같은 청산 방식이
# 앞선다면 신호에 가깝고, 구간마다 1등이 바뀌면 과최적화로 봐야 한다.
#
# 전체 구간: 2020-08-28 ~ 2026-09-04 (직전 실행 기준)
# 반으로 가르는 지점: 2023-09-01

set -u
cd "$(dirname "$0")"

MODES="target,ma50,trail20,half_ma50"
POS="3,5,10"

run () {   # $1=label  $2=start  $3=end  $4=outdir
  echo ""
  echo "════════════════════════════════════════════════════════"
  echo "  $1  ($2 ~ $3)"
  echo "════════════════════════════════════════════════════════"
  python backtest.py \
    --years 6 --positions "$POS" --exit-modes "$MODES" \
    --start "$2" --end "$3" --label "$1" --out "$4"
}

run "전반부" 2020-08-28 2023-09-01 data/bt_split/first
run "후반부" 2023-09-01 2026-09-04 data/bt_split/second

echo ""
echo "구간 분할 검증 완료"
