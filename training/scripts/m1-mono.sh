#!/usr/bin/env bash
# Control: two monolingual models, each half the size of s5 (same total bytes), vs one mixed model.
set -euo pipefail
cd "$(dirname "$0")/.."
S=nemotron:1,openpii:1,templates:0.5,hardneg:0.5,synth:0.5
scripts/stage.sh mono-zh "$S" --buckets 32768 --langs zh,mixed
scripts/stage.sh mono-en "$S" --buckets 32768 --langs en
uv run python py/merge_preds.py mono model-mono-zh model-mono-en
echo mono-done
