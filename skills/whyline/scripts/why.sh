#!/bin/sh
# Stable wrapper around `whyline why`.
# A missing install or a line with no record exits 0 and says so.
# Any other whyline failure is passed through.
set -eu
if ! command -v whyline >/dev/null 2>&1; then
    echo "No record: whyline is not on PATH."
    exit 0
fi
exec whyline why "$@"
