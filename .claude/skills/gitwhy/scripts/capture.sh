#!/bin/sh
# Stable wrapper around `gitwhy capture`. Forwards every argument.
# Exits non-zero with a clear message when gitwhy is not installed.
set -eu
if ! command -v gitwhy >/dev/null 2>&1; then
    echo "gitwhy is not on PATH. Install it with: uv tool install gitwhy" >&2
    exit 127
fi
exec gitwhy capture "$@"
