#!/bin/sh
# Stable wrapper around `whyline capture`. Forwards every argument.
# Exits non-zero with a clear message when whyline is not installed.
set -eu
if ! command -v whyline >/dev/null 2>&1; then
    echo "whyline is not on PATH. Install it with: uv tool install whyline" >&2
    exit 127
fi
exec whyline capture "$@"
