# gitwhy-managed: begin. `gitwhy uninstall-hooks` removes the lines up to the end marker.
# Adds a Gitwhy-Id trailer from .gitwhy/pending. Never blocks a commit.
if command -v gitwhy >/dev/null 2>&1; then
  gitwhy hook prepare-commit-msg "$@" || echo "gitwhy: hook failed; committing without a Gitwhy-Id trailer" >&2
else
  echo "gitwhy: not found on PATH; committing without a Gitwhy-Id trailer" >&2
fi
# gitwhy-managed: end
