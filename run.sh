#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
if [[ -x "$DIR/venv/bin/python" ]]; then
  PYTHON="$DIR/venv/bin/python"
fi
exec "$PYTHON" -X utf8 "$DIR/scripts/icj_search.py" "$@"
