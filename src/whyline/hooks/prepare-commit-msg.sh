# whyline-managed: begin. `whyline uninstall-hooks` removes the lines up to the end marker.
# Adds a Whyline-Id trailer from .whyline/pending. Never blocks a commit.
if command -v whyline >/dev/null 2>&1; then
  whyline hook prepare-commit-msg "$@" || echo "whyline: hook failed; committing without a Whyline-Id trailer" >&2
else
  echo "whyline: not found on PATH; committing without a Whyline-Id trailer" >&2
fi
# whyline-managed: end
