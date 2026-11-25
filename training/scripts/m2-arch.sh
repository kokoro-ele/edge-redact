#!/usr/bin/env bash
# M2: cheaper architectures on s5 data (64k × 32 embedding table kept; only the conv stack changes).
set -euo pipefail
cd "$(dirname "$0")/.."
S=nemotron:1,openpii:1,templates:0.5,hardneg:0.5,synth:0.5
scripts/stage.sh ds96 "$S" --sep --hidden 96
scripts/stage.sh ds64 "$S" --sep --hidden 64
scripts/stage.sh ds64x6 "$S" --sep --hidden 64 --dilations 1,2,4,8,4,1
scripts/stage.sh ds48 "$S" --sep --hidden 48
scripts/stage.sh fc48 "$S" --hidden 48
echo arch-done
