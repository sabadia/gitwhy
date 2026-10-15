"""Copy the public docs to the GitHub wiki.

The wiki is a flat git repository. This script rewrites links so each guide
becomes one wiki page, then optionally pushes ``master``.

Usage:
    python3 scripts/sync_wiki.py /path/to/intentline.wiki
    python3 scripts/sync_wiki.py /path/to/intentline.wiki --push
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# Source path relative to docs/ -> wiki page filename.
PAGES: dict[str, str] = {
    "README.md": "Home.md",
    "installation.md": "Installation.md",
    "getting-started.md": "Getting-Started.md",
    "records.md": "Records.md",
    "capture.md": "Capture.md",
    "linking.md": "Linking.md",
    "recall.md": "Recall.md",
    "affirm.md": "Affirm.md",
    "check.md": "Check.md",
    "hooks.md": "Hooks.md",
    "configuration.md": "Configuration.md",
    "agents.md": "Agents.md",
    "adapters/claude-code.md": "Claude-Code.md",
    "adapters/other-agents.md": "Other-Agents.md",
    "exit-codes.md": "Exit-Codes.md",
    "limits.md": "Limits.md",
    "troubleshooting.md": "Troubleshooting.md",
    "contributing.md": "Contributing.md",
}

LINK = re.compile(r"\]\(([^)#]+)(#[^)]+)?\)")


def _rewrite(text: str, source: str) -> str:
    """Point relative doc links at flat wiki pages."""

    def replace(match: re.Match[str]) -> str:
        target, anchor = match.group(1), match.group(2) or ""
        if target.startswith(("http://", "https://", "mailto:")):
            return match.group(0)
        here = (DOCS / source).parent
        resolved = (here / target).resolve()
        try:
            rel = resolved.relative_to(DOCS.resolve()).as_posix()
        except ValueError:
            return match.group(0)
        page = PAGES.get(rel)
        if page is None:
            return match.group(0)
        # Wiki pages render at /wiki/Name. A link to Name.md is the raw file.
        return f"]({page.removesuffix('.md')}{anchor})"

    return LINK.sub(replace, text)


def _sidebar() -> str:
    lines = ["# Intentline", ""]
    for source, page in PAGES.items():
        if source == "README.md":
            continue
        title = page.removesuffix(".md").replace("-", " ")
        lines.append(f"- [{title}]({page.removesuffix('.md')})")
    lines.append("")
    return "\n".join(lines)


def sync(wiki: Path) -> list[Path]:
    """Write wiki pages. Returns the paths written."""
    written: list[Path] = []
    for source, page in PAGES.items():
        text = (DOCS / source).read_text(encoding="utf-8")
        dest = wiki / page
        dest.write_text(_rewrite(text, source), encoding="utf-8")
        written.append(dest)
    sidebar = wiki / "_Sidebar.md"
    sidebar.write_text(_sidebar(), encoding="utf-8")
    written.append(sidebar)
    footer = wiki / "_Footer.md"
    footer.write_text(
        "Intentline manual. The source of these pages is `docs/` in the repository.\n",
        encoding="utf-8",
    )
    written.append(footer)
    return written


def _git(wiki: Path, *args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run git in the wiki checkout. ``git`` is resolved to an absolute path."""
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git is not on PATH")
    return subprocess.run(  # noqa: S603
        [git, "-C", str(wiki), *args],
        check=True,
        capture_output=capture,
        text=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wiki", type=Path, help="Checkout of sabadia/intentline.wiki")
    parser.add_argument("--push", action="store_true", help="Commit and push master")
    args = parser.parse_args()
    wiki: Path = args.wiki
    if not (wiki / ".git").is_dir():
        raise SystemExit(f"{wiki} is not a git checkout")
    sync(wiki)
    if not args.push:
        print(f"Wrote wiki pages in {wiki}")
        return
    _git(wiki, "add", "-A")
    status = _git(wiki, "status", "--porcelain", capture=True)
    if not status.stdout.strip():
        print("Wiki already matches docs/")
        return
    _git(wiki, "commit", "-m", "docs: sync the manual from docs/")
    _git(wiki, "push", "origin", "HEAD")
    print("Pushed the wiki")


if __name__ == "__main__":
    main()
