#!/usr/bin/env bash
# API integration tests and security rules tests, against the Firebase emulators.
# Needs Java 21+ on PATH. Uses the offline demo-travelin project, never the real one.
set -euo pipefail
cd "$(dirname "$0")/.."

GOOGLE_CLOUD_PROJECT=demo-travelin npx firebase-tools emulators:exec \
  --only firestore,auth,storage --project demo-travelin \
  "cd api && uv run pytest -q -p no:warnings && cd ../firebase && npm test"
