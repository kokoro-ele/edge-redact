#!/usr/bin/env bash
# s5 (+ synthetic zh/zh-en templates), then the size sweep on the same data.
set -euo pipefail
cd "$(dirname "$0")/.."
S=nemotron:1,openpii:1,templates:0.5,hardneg:0.5,synth:0.5
scripts/stage.sh s5-synth "$S"
scripts/stage.sh s5-xs "$S" --buckets 16384 --emb 16 --hidden 48
scripts/stage.sh s5-sm "$S" --buckets 32768 --emb 24 --hidden 64
scripts/stage.sh s5-lg "$S" --buckets 131072 --emb 32 --hidden 128
# teachers and earlier stages on the new held-out synth sets, for comparison
for t in gliner-multi-pii gliner-pii-nvidia ai4privacy-modernbert; do
  uv run --extra teacher python py/teacher.py "$t" --sets zh-synth,mixed-synth | tail -1
done
for m in s3-templates s4-hardneg; do uv run --extra train python py/predict.py "$m" > /dev/null; done
echo all-done
