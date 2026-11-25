#!/usr/bin/env bash
# Train one M1 stage, pick thresholds on dev, write predictions for `pnpm bench` and `pnpm rbench`.
#   scripts/stage.sh <name> <sources> [extra train.py args, e.g. --buckets 16384 --emb 16 --hidden 48]
set -euo pipefail
cd "$(dirname "$0")/.."
name=$1; sources=$2; shift 2
uv run --extra train python py/train.py "$name" --sources "$sources" "$@" | tail -2
uv run --extra train python py/tune.py "$name" | tail -1
uv run --extra train python py/predict.py "$name" > /dev/null
uv run --extra train python py/predict.py "$name" --ext > /dev/null
echo "stage $name done"
