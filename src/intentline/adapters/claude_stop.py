"""Stop-hook entry. Reads the hook payload on stdin, drafts at most one record, always exits 0."""

import sys

from intentline.adapters.claude import run_stop_hook


def main() -> None:
    """Run the Stop hook. Never raises. The process exits 0."""
    try:
        run_stop_hook(sys.stdin.read())
    except Exception:
        # run_stop_hook already swallows its own failures. This is the last boundary.
        return
