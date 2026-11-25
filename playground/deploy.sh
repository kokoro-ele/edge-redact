#!/usr/bin/env bash
# Build locally (the page imports ../src, which a remote build of this folder would not see) and upload
# the static output as the Vercel project "edge-redact".
set -euo pipefail
cd "$(dirname "$0")"
pnpm build
rm -rf .deploy && mkdir -p .deploy && cp -R dist .deploy/edge-redact && cp vercel.json .deploy/edge-redact/
# README demo GIFs live in ../media (not in git) and are served from the playground
if compgen -G "../media/demo-*.gif" > /dev/null; then cp ../media/demo-*.gif .deploy/edge-redact/; fi
cd .deploy/edge-redact
vercel deploy --prod --yes "$@"
