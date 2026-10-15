# intentline-managed: begin. `intentline uninstall-hooks` removes the lines up to the end marker.
# Adds a Intentline-Id trailer from .intentline/pending. Never blocks a commit.
if command -v intentline >/dev/null 2>&1; then
  intentline hook prepare-commit-msg "$@" || echo "intentline: hook failed; committing without a Intentline-Id trailer" >&2
else
  echo "intentline: not found on PATH; committing without a Intentline-Id trailer" >&2
fi
# intentline-managed: end
