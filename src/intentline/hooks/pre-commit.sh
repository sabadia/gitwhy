# intentline-managed: begin. `intentline uninstall-hooks` removes the lines up to the end marker.
# Runs `intentline check` when hooks.check (or check.enabled) is true in .intentline/config.yml.
# Blocks the commit only when check says a record is needed; anything else lets it through.
if command -v intentline >/dev/null 2>&1; then
  intentline hook pre-commit
  if [ "$?" -eq 3 ]; then
    exit 1
  fi
else
  echo "intentline: not found on PATH; skipping intentline check" >&2
fi
# intentline-managed: end
