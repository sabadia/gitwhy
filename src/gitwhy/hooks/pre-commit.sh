# gitwhy-managed: begin. `gitwhy uninstall-hooks` removes the lines up to the end marker.
# Runs `gitwhy check` when hooks.check (or check.enabled) is true in .gitwhy/config.yml.
# Blocks the commit only when check says a record is needed; anything else lets it through.
if command -v gitwhy >/dev/null 2>&1; then
  gitwhy hook pre-commit
  if [ "$?" -eq 3 ]; then
    exit 1
  fi
else
  echo "gitwhy: not found on PATH; skipping gitwhy check" >&2
fi
# gitwhy-managed: end
