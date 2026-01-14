#!/bin/bash
set -e

usage() {
  cat << EOF
Usage: $0 <algorithm> <start> <end>
       $0 ai <benchmark_data.json> [-m mistral:latest]

Arguments:
  algorithm           cs_jp_lp, rs_jp, both, or ai
  start               Starting case number (for cs_jp_lp, rs_jp, both)
  end                 Ending case number (for cs_jp_lp, rs_jp, both)
  benchmark_data.json Path to benchmark JSON file (for ai)

AI Evaluation Options:
  -m, --model MODEL         Ollama model to use (default: mistral:latest)
  -o, --output-dir DIR      Output directory (default: ./results)
  --ollama-host HOST        Ollama API host (default: http://0.0.0.0:11434)

Examples:
  $0 cs_jp_lp 1 50
  $0 rs_jp 1 50
  $0 both 1 50
  $0 ai eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_data.json
  $0 ai benchmark_data.json -m mistral:latest
EOF
  exit 1
}

[ $# -eq 0 ] && usage

ALGORITHM="$1"

# Check for AI benchmarking mode
if [ "$ALGORITHM" = "ai" ]; then
  shift  # Remove 'ai' from arguments
  [ $# -eq 0 ] && echo "Error: Missing arguments for AI benchmarking mode. Use -i <file>" && usage
  echo "Running AI benchmarking mode"
  cd python-service && uv sync && cd .. && uv run --directory python-service benchmark_ai_rs_jp.py "$@"
  exit 0
fi

# Regular benchmark mode
[ $# -eq 2 ] && echo "Error: Missing end parameter" && usage
[ $# -ne 3 ] && echo "Error: Expected 3 arguments for regular benchmark mode" && usage

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
