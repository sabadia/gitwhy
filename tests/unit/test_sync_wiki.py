"""Wiki links must name the rendered page, not the raw Markdown file."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync_wiki.py"


def _sync_wiki():
    spec = importlib.util.spec_from_file_location("sync_wiki", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wiki_page_links_drop_the_markdown_extension() -> None:
    module = _sync_wiki()
    text = module._rewrite(
        "[Install](installation.md)\n[Hook](adapters/claude-code.md#stop)\n",
        "README.md",
    )
    assert "](Installation)" in text
    assert "](Claude-Code#stop)" in text
    assert ".md)" not in text


def test_external_and_unknown_links_keep_their_suffix() -> None:
    module = _sync_wiki()
    text = module._rewrite(
        "[uv](https://docs.astral.sh/uv/install.md)\n[notes](missing.md)\n",
        "README.md",
    )
    assert "https://docs.astral.sh/uv/install.md" in text
    assert "](missing.md)" in text


def test_sidebar_links_are_rendered_pages() -> None:
    sidebar = _sync_wiki()._sidebar()
    assert "](Installation)" in sidebar
    assert ".md)" not in sidebar
