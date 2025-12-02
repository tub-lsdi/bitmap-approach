#!/bin/bash

# Exit on errors
set -e

if [ $# -ne 2 ]; then
  echo "Usage: $0 <start> <end>"
  exit 1
fi

START="$1"
END="$2"

docker compose run --rm python-service uv run benchmark_cs_jp_lp.py --start "$START" --end "$END"
