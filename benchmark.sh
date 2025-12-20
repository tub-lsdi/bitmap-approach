#!/bin/bash
set -e

usage() {
  cat << EOF
Usage: $0 <algorithm> <start> <end>

Arguments:
  algorithm    cs_jp_lp, rs_jp, or both
  start        Starting case number
  end          Ending case number

Examples:
  $0 cs_jp_lp 1 50
  $0 rs_jp 1 50
  $0 both 1 50
EOF
  exit 1
}

[ $# -eq 2 ] && echo "Error: Missing algorithm parameter" && usage
[ $# -ne 3 ] && usage

ALGORITHM="$1"
START="$2"
END="$3"

[[ ! "$ALGORITHM" =~ ^(cs_jp_lp|rs_jp|both)$ ]] && echo "Error: Invalid algorithm '$ALGORITHM'" && usage
[[ ! "$START" =~ ^[0-9]+$ ]] || [[ ! "$END" =~ ^[0-9]+$ ]] && echo "Error: Start and end must be numbers" && usage
[ "$START" -gt "$END" ] && echo "Error: Start must be <= end" && exit 1

run_cs_jp_lp() {
  echo "Running CS-JP-LP: Cases $START-$END"
  docker compose run --rm python-service uv run benchmark_cs_jp_lp.py --start "$START" --end "$END"
}

run_rs_jp() {
  echo "Running RS-JP: Cases $START-$END"
  docker compose run --rm python-service uv run benchmark_rs_jp.py --start "$START" --end "$END"
}

case "$ALGORITHM" in
  cs_jp_lp) run_cs_jp_lp ;;
  rs_jp) run_rs_jp ;;
  both)
    echo "Running both algorithms: Cases $START-$END"
    echo ""
    run_cs_jp_lp
    echo ""
    run_rs_jp
    echo ""
    echo "Done!"
    ;;
esac
