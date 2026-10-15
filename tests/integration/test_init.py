"""``whyline init`` against real git repositories (docs/03 section 4, docs/05 section 2)."""

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from tests.conftest import MakeRecord, plain, uuid7
from whyline.cli import app
from whyline.config import load_config
from whyline.errors import CorruptError, NoRepoError
from whyline.gitio import config_value, repo_root
from whyline.models import Config
from whyline.store import RecordStore, default_config_text, initialize

runner = CliRunner()

LAYOUT = [
    ".whyline/config.yml",
    ".whyline/schema-version",
    ".whyline/records/.gitkeep",
    ".whyline/.gitignore",
]


def _init(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> tuple[int, str]:
    monkeypatch.chdir(repo)
    result = runner.invoke(app, ["init", *args])
    return result.exit_code, plain(result.output)


def test_init_creates_layout(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _init(git_repo, monkeypatch)
    assert code == 0, output
    for rel in LAYOUT:
        assert (git_repo / rel).is_file(), rel
    whyline = git_repo / ".whyline"
    assert (whyline / "schema-version").read_text() == "1\n"
    assert (whyline / ".gitignore").read_text() == "pending\n"
    config = Config.model_validate(yaml.safe_load((whyline / "config.yml").read_text()))
    assert config == Config()
    assert "created .whyline/config.yml" in output
    assert "Commit .whyline/" in output


def test_init_from_subdirectory_uses_repo_root(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = git_repo / "src" / "pkg"
    sub.mkdir(parents=True)
    code, _ = _init(sub, monkeypatch)
    assert code == 0
    assert (git_repo / ".whyline" / "config.yml").is_file()
    assert not (sub / ".whyline").exists()


def test_init_twice_is_a_no_op(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(git_repo, monkeypatch)
    config = git_repo / ".whyline" / "config.yml"
    config.write_text("check:\n  min_lines: 99\n", encoding="utf-8")
    before = {rel: (git_repo / rel).read_bytes() for rel in LAYOUT}

    code, output = _init(git_repo, monkeypatch)

    assert code == 0
    assert "Nothing changed" in output
    assert {rel: (git_repo / rel).read_bytes() for rel in LAYOUT} == before


def test_init_force_resets_config_but_keeps_records(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, make_record: MakeRecord
) -> None:
    _init(git_repo, monkeypatch)
    config = git_repo / ".whyline" / "config.yml"
    config.write_text("check:\n  min_lines: 99\n", encoding="utf-8")
    record_path = RecordStore(git_repo / ".whyline").save(make_record())
    record_bytes = record_path.read_bytes()

    code, output = _init(git_repo, monkeypatch, "--force")

    assert code == 0
    assert config.read_text(encoding="utf-8") == default_config_text()
    assert "updated .whyline/config.yml" in output
    assert record_path.read_bytes() == record_bytes
    assert RecordStore(git_repo / ".whyline").load(uuid7(1)).goal == "Goal number 1"


def test_init_outside_a_repo_exits_2_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    code, output = _init(plain, monkeypatch)
    assert code == 2
    assert "Not inside a git work tree" in output
    assert list(plain.iterdir()) == []


@pytest.mark.parametrize("force", [False, True])
def test_init_refuses_newer_schema_even_with_force(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, force: bool
) -> None:
    whyline = git_repo / ".whyline"
    whyline.mkdir()
    (whyline / "schema-version").write_text("2\n", encoding="utf-8")
    code, output = _init(git_repo, monkeypatch, *(["--force"] if force else []))
    assert code == 6
    assert "Upgrade whyline" in plain(output)
    assert (whyline / "schema-version").read_text() == "2\n"
    assert not (whyline / "config.yml").exists()


def test_init_garbled_schema_version_needs_force(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    whyline = git_repo / ".whyline"
    whyline.mkdir()
    (whyline / "schema-version").write_text("banana\n", encoding="utf-8")

    code, output = _init(git_repo, monkeypatch)
    assert code == 4
    assert "whyline init --force" in plain(output)

    code, output = _init(git_repo, monkeypatch, "--force")
    assert code == 0
    assert (whyline / "schema-version").read_text() == "1\n"
    assert "updated .whyline/schema-version" in output


def test_init_keeps_existing_gitignore_lines(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    whyline = git_repo / ".whyline"
    whyline.mkdir()
    (whyline / ".gitignore").write_text("index.json", encoding="utf-8")
    code, _ = _init(git_repo, monkeypatch)
    assert code == 0
    assert (whyline / ".gitignore").read_text() == "index.json\npending\n"


def test_init_does_not_duplicate_pending_line(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    whyline = git_repo / ".whyline"
    whyline.mkdir()
    (whyline / ".gitignore").write_text("# local state\n  pending  \n", encoding="utf-8")
    _init(git_repo, monkeypatch)
    assert (whyline / ".gitignore").read_text() == "# local state\n  pending  \n"


def test_init_fills_in_a_partial_layout(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    whyline = git_repo / ".whyline"
    whyline.mkdir()
    (whyline / "config.yml").write_text("hooks:\n  check: true\n", encoding="utf-8")
    code, output = _init(git_repo, monkeypatch)
    assert code == 0
    assert (whyline / "config.yml").read_text() == "hooks:\n  check: true\n"
    assert (whyline / "records" / ".gitkeep").is_file()
    assert "created .whyline/records" in output


def test_init_verbose_lists_unchanged(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(git_repo, monkeypatch)
    code, output = _init(git_repo, monkeypatch, "--verbose")
    assert code == 0
    assert "unchanged .whyline/config.yml" in output


def test_whyline_path_that_is_a_file_is_corrupt(git_repo: Path) -> None:
    (git_repo / ".whyline").write_text("oops", encoding="utf-8")
    with pytest.raises(CorruptError, match="not a directory"):
        initialize(git_repo)


def test_initialized_repo_works_with_the_store(git_repo: Path, make_record: MakeRecord) -> None:
    initialize(git_repo)
    store = RecordStore(git_repo / ".whyline")
    store.save(make_record())
    result = store.list()
    assert [r.id for r in result.records] == [uuid7(1)]
    assert result.errors == []


# --- gitio -------------------------------------------------------------------------------------


def test_repo_root_from_nested_directory(git_repo: Path) -> None:
    nested = git_repo / "a" / "b"
    nested.mkdir(parents=True)
    assert repo_root(nested) == git_repo


def test_repo_root_without_git_installed(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("whyline.gitio.shutil.which", lambda name: None)
    with pytest.raises(NoRepoError, match="git is not installed"):
        repo_root(git_repo)


def test_git_config_value(git_repo: Path) -> None:
    subprocess.run(["git", "-C", str(git_repo), "config", "user.name", "Ada Lovelace"], check=True)  # noqa: S603, S607
    assert config_value("user.name", git_repo) == "Ada Lovelace"
    assert config_value("whyline.nonexistent", git_repo) is None


# --- #57: the project config written by init must not mask the user config ----------------


def _nested_keys(data: dict[str, object]) -> list[str]:
    found: list[str] = []
    for key, value in data.items():
        found.append(key)
        if isinstance(value, dict):
            found.extend(_nested_keys(value))
    return found


def test_init_does_not_mask_user_config(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, isolated_user_config: Path
) -> None:
    (isolated_user_config / "config.yml").write_text(
        "capture:\n  default_author_name: Ada\ncheck:\n  min_lines: 10\n", encoding="utf-8"
    )
    code, _ = _init(git_repo, monkeypatch)
    assert code == 0
    config = load_config(git_repo)
    assert config.capture.default_author_name == "Ada"
    assert config.check.min_lines == 10


def test_init_config_sets_only_schema_version(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(git_repo, monkeypatch)
    text = (git_repo / ".whyline" / "config.yml").read_text(encoding="utf-8")
    assert yaml.safe_load(text) == {"schema_version": 1}
    assert load_config(git_repo) == Config()


def test_init_config_documents_every_default_key() -> None:
    commented = "\n".join(
        line[2:] for line in default_config_text().splitlines() if line.startswith("# ")
    )
    for key in _nested_keys(Config().model_dump(mode="json")):
        if key != "schema_version":
            assert f"{key}:" in commented, key


def test_init_force_writes_the_minimal_config(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(git_repo, monkeypatch)
    config = git_repo / ".whyline" / "config.yml"
    config.write_text("check:\n  min_lines: 99\n", encoding="utf-8")
    _init(git_repo, monkeypatch, "--force")
    assert config.read_text(encoding="utf-8") == default_config_text()
    assert yaml.safe_load(config.read_text(encoding="utf-8")) == {"schema_version": 1}
