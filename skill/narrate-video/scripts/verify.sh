#!/bin/sh
set -eu
SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"${PYTHON:-python3}" -m unittest discover -s "$SKILL_DIR/tests" -v
if [ "$#" -gt 0 ]; then
  node "$SKILL_DIR/tests/test_capture.mjs" "$@"
fi
