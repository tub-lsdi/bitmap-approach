#!/bin/bash
set -e

usage() {
  cat << EOF
Usage: $0 <algorithm> <start> <end>
       $0 ai <benchmark_data.json> [options]
       $0 ai_naiv <benchmark_data.json> [options]

Arguments:
  algorithm           cs_jp_lp, rs_jp, both, ai, or ai_naiv
  start               Starting case number (for cs_jp_lp, rs_jp, both)
  end                 Ending case number (for cs_jp_lp, rs_jp, both)
  benchmark_data.json Path to benchmark JSON file (for ai, ai_naiv)

AI Evaluation Options (for 'ai' and 'ai_naiv'):
  -i, --input FILE          Input benchmark JSON file (required)
  -m, --model MODEL         Ollama model to use (default: mistral:latest)
  -o, --output-dir DIR      Output directory (default: ./results)
  --ollama-host HOST        Ollama API host (default: http://0.0.0.0:11434)
  --benchmark-data-dir DIR  Benchmark data directory (default: ./benchmark-data) [ai only]
  --random-seed SEED        Random seed for reproducibility [ai only]

Algorithms:
  ai        - Context-enhanced AI evaluation (2-step with random sampling)
  ai_naiv   - Naive AI evaluation (single-step, no context)

Examples:
  $0 cs_jp_lp 1 50
  $0 rs_jp 1 50
  $0 both 1 50
  $0 ai -i results/benchmark_rs_jp_duckdb_20260113_154339.json --random-seed 42
  $0 ai_naiv -i results/benchmark_rs_jp_duckdb_20260113_154339.json
  $0 ai -i benchmark_data.json -m mistral:latest --random-seed 42
EOF
  exit 1
}

[ $# -eq 0 ] && usage

ALGORITHM="$1"

# Check for AI benchmarking mode
if [ "$ALGORITHM" = "ai" ]; then
  shift  # Remove 'ai' from arguments
  [ $# -eq 0 ] && echo "Error: Missing arguments for AI benchmarking mode. Use -i <file>" && usage
  echo "Running AI benchmarking mode (Context)"
  cd python-service && uv sync && cd .. && uv run --directory python-service benchmark_ai_rs_jp.py "$@"
  exit 0
fi

# Check for AI naive benchmarking mode
if [ "$ALGORITHM" = "ai_naiv" ]; then
  shift  # Remove 'ai_naiv' from arguments
  [ $# -eq 0 ] && echo "Error: Missing arguments for AI naive benchmarking mode. Use -i <file>" && usage
  echo "Running AI benchmarking mode (Naive)"
  cd python-service && uv sync && cd .. && uv run --directory python-service benchmark_ai_rs_jp_naiv.py "$@"
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
