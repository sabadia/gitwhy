#!/bin/sh
# Stable wrapper around `gitwhy why`.
# A missing install or a line with no record exits 0 and says so.
# Any other gitwhy failure is passed through.
set -eu
if ! command -v gitwhy >/dev/null 2>&1; then
    echo "No record: gitwhy is not on PATH."
    exit 0
fi
exec gitwhy why "$@"
