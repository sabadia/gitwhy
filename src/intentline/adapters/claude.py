"""Claude Code Stop hook: print it, merge it, and draft from the session it points at.

The session file is ``transcript_path`` on the hook's stdin. Claude Code documents that field
on every hook payload (https://code.claude.com/docs/en/hooks). The on-disk directory under
``~/.claude/projects`` is not a stable path, so this module never guesses one.
"""

import json
from pathlib import Path
from typing import Any

from intentline.capture import CaptureInput, capture
from intentline.errors import CorruptError
from intentline.gitio import repo_root, staged_paths
from intentline.session import read_session, session_files_in_repo, session_source_ref
from intentline.store import INTENTLINE_DIRNAME, RecordStore, read_pending

STOP_COMMAND = (
    "sh -c 'command -v intentline >/dev/null 2>&1 || exit 0; intentline adapters claude-stop'"
)
"""Shell command Claude Code runs. Exits 0 when intentline is not on PATH."""

HOOK_NOTE = (
    "Claude Code sends the session file as transcript_path on this hook's stdin\n"
    "(https://code.claude.com/docs/en/hooks). The hook does not guess a directory\n"
    "under ~/.claude/projects. It writes a draft only when that file exists, the\n"
    "session lists files or something is staged, and .intentline/pending is empty.\n"
    "It never affirms. If intentline is not on PATH, the hook exits 0.\n"
)

_SETTINGS = Path(".claude") / "settings.json"
_FIX = "Fix the file, or move it aside and run `intentline adapters claude --write` again."


def claude_hook_snippet() -> dict[str, Any]:
    """Return the Stop hook object merged into ``.claude/settings.json``."""
    return {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": STOP_COMMAND,
                            "timeout": 10,
                        }
                    ]
                }
            ]
        }
    }


def _has_command(value: object, command: str) -> bool:
    if isinstance(value, dict):
        if value.get("command") == command:
            return True
        return any(_has_command(item, command) for item in value.values())
    if isinstance(value, list):
        return any(_has_command(item, command) for item in value)
    return False


def _corrupt(path: Path, problem: str) -> CorruptError:
    return CorruptError(f"{path} {problem}.", hint=_FIX)


def merge_claude_settings(
    existing: dict[str, Any] | None, *, path: Path
) -> tuple[dict[str, Any], bool]:
    """Return settings with the Stop hook added, and whether that changed them.

    ``path`` is only named in errors. An existing command equal to ``STOP_COMMAND`` is left
    in place, so a second write does not append a second hook.
    """
    snippet = claude_hook_snippet()
    if existing is None:
        return snippet, True
    hooks = existing.get("hooks")
    if hooks is None:
        merged = dict(existing)
        merged["hooks"] = snippet["hooks"]
        return merged, True
    if not isinstance(hooks, dict):
        raise _corrupt(path, "has a hooks value that is not a JSON object")
    stop = hooks.get("Stop")
    addition = snippet["hooks"]["Stop"]
    if stop is None:
        merged_hooks = dict(hooks)
        merged_hooks["Stop"] = addition
        merged = dict(existing)
        merged["hooks"] = merged_hooks
        return merged, True
    if not isinstance(stop, list):
        raise _corrupt(path, "has a hooks.Stop value that is not a JSON array")
    if any(_has_command(entry, STOP_COMMAND) for entry in stop):
        return existing, False
    merged_hooks = dict(hooks)
    merged_hooks["Stop"] = [*stop, *addition]
    merged = dict(existing)
    merged["hooks"] = merged_hooks
    return merged, True


def write_claude_settings(root: Path) -> bool:
    """Merge the Stop hook into ``root/.claude/settings.json``. Return True if it changed.

    A missing file is created. A file that already runs ``STOP_COMMAND`` is not rewritten.
    A file that is not a JSON object raises ``CorruptError`` and is left untouched.
    """
    path = root / _SETTINGS
    existing: dict[str, Any] | None
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _corrupt(path, "is not JSON") from exc
        if not isinstance(loaded, dict):
            raise _corrupt(path, "is not a JSON object")
        existing = loaded
    else:
        existing = None
    merged, changed = merge_claude_settings(existing, path=path)
    if not changed:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return True


def run_stop_hook(payload: str, *, cwd: Path | None = None) -> int:
    """Draft at most one record from a Stop hook payload. Always returns 0.

    A failure here must not block the agent, so every exception becomes 0.
    """
    try:
        _capture_from_stop(payload, cwd if cwd is not None else Path.cwd())
    except Exception:
        # A Stop hook must never block the agent: top-level safety boundary.
        return 0
    return 0


def _capture_from_stop(payload: str, cwd: Path) -> None:
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        return
    if loaded.get("stop_hook_active") is True:
        return
    transcript = loaded.get("transcript_path")
    if not isinstance(transcript, str) or not transcript.strip():
        return
    session = Path(transcript)
    if not session.is_file():
        return
    root = repo_root(cwd)
    store = RecordStore(root / INTENTLINE_DIRNAME)
    store.require_initialized()
    if read_pending(store.intentline_dir) is not None:
        return
    facts = read_session(session)
    if facts.goal is None:
        return
    files = session_files_in_repo(facts.files, root)
    if not files and not staged_paths(root):
        return
    capture(
        CaptureInput(
            goal=facts.goal,
            files=files,
            agent_tool="claude-code",
            source_kind="session",
            source_ref=session_source_ref(session, root),
        ),
        root=root,
        cwd=cwd,
        pending=True,
    )
