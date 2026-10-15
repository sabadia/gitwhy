# whyline-managed: begin. `whyline uninstall-hooks` removes the lines up to the end marker.
# Runs `whyline check` when hooks.check (or check.enabled) is true in .whyline/config.yml.
# Blocks the commit only when check says a record is needed; anything else lets it through.
if command -v whyline >/dev/null 2>&1; then
  whyline hook pre-commit
  if [ "$?" -eq 3 ]; then
    exit 1
  fi
else
  echo "whyline: not found on PATH; skipping whyline check" >&2
fi
# whyline-managed: end
