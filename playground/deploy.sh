#!/usr/bin/env bash
# Build locally (the page imports ../src, which a remote build of this folder would not see) and upload
# the static output as the Vercel project "edge-redact".
set -euo pipefail
cd "$(dirname "$0")"
pnpm build
rm -rf .deploy && mkdir -p .deploy && cp -R dist .deploy/edge-redact && cp vercel.json .deploy/edge-redact/
cd .deploy/edge-redact
vercel deploy --prod --yes "$@"
