"""Layered config loading (docs/02 section 5)."""

from datetime import UTC
from pathlib import Path

import pytest

from whyline.config import load_config, project_config_path, read_config_file, user_config_path
from whyline.errors import CorruptError, SchemaVersionError
from whyline.models import Config, utc_now


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_when_no_files(tmp_path: Path) -> None:
    assert load_config(tmp_path) == Config()


def test_project_overrides_user_overrides_defaults(
    tmp_path: Path, isolated_user_config: Path
) -> None:
    _write(
        isolated_user_config / "config.yml",
        "check:\n  min_lines: 10\n  enabled: true\ncapture:\n  default_author_name: Ada\n",
    )
    _write(project_config_path(tmp_path), "check:\n  min_lines: 50\n")
    config = load_config(tmp_path)
    assert config.check.min_lines == 50  # project wins
    assert config.check.enabled is True  # user value kept where project is silent
    assert config.capture.default_author_name == "Ada"  # user value
    assert config.hooks.trailer is True  # default


def test_lists_replace_rather_than_merge(tmp_path: Path, isolated_user_config: Path) -> None:
    _write(isolated_user_config / "config.yml", "check:\n  ignore: ['a']\n")
    _write(project_config_path(tmp_path), "check:\n  ignore: ['b']\n")
    assert load_config(tmp_path).check.ignore == ["b"]


def test_explicit_user_path(tmp_path: Path) -> None:
    user = _write(tmp_path / "elsewhere.yml", "hooks:\n  check: true\n")
    assert load_config(tmp_path, user_path=user).hooks.check is True


def test_empty_files_are_defaults(tmp_path: Path, isolated_user_config: Path) -> None:
    _write(isolated_user_config / "config.yml", "")
    _write(project_config_path(tmp_path), "# only a comment\n")
    assert load_config(tmp_path) == Config()


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("check: [unclosed\n", "not valid YAML"),
        ("- a\n- b\n", "not a YAML mapping"),
        ("chek:\n  min_lines: 1\n", "failed validation"),
        ("check:\n  min_lines: -3\n", "failed validation"),
    ],
)
def test_bad_project_config_is_corrupt_and_named(tmp_path: Path, text: str, match: str) -> None:
    path = _write(project_config_path(tmp_path), text)
    with pytest.raises(CorruptError, match=match) as excinfo:
        load_config(tmp_path)
    assert str(path) in str(excinfo.value)
    assert "Project config" in str(excinfo.value)


def test_bad_user_config_is_corrupt_and_named(tmp_path: Path, isolated_user_config: Path) -> None:
    _write(isolated_user_config / "config.yml", "hooks:\n  trailer: sometimes\n")
    with pytest.raises(CorruptError, match="User config"):
        load_config(tmp_path)


def test_unreadable_config_is_corrupt(tmp_path: Path) -> None:
    path = project_config_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(CorruptError, match="Cannot read"):
        read_config_file(path, label="Project config")


def test_newer_config_schema_exits_6(tmp_path: Path) -> None:
    _write(project_config_path(tmp_path), "schema_version: 2\n")
    with pytest.raises(SchemaVersionError):
        load_config(tmp_path)


def test_user_config_path_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert user_config_path({"WHYLINE_CONFIG_HOME": "/w"}) == Path("/w/config.yml")
    assert user_config_path({"XDG_CONFIG_HOME": "/x"}) == Path("/x/whyline/config.yml")
    assert user_config_path({"WHYLINE_CONFIG_HOME": "/w", "XDG_CONFIG_HOME": "/x"}) == Path(
        "/w/config.yml"
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    assert user_config_path({}) == tmp_path / ".config" / "whyline" / "config.yml"


def test_default_user_config_path_uses_environment(isolated_user_config: Path) -> None:
    assert user_config_path() == isolated_user_config / "config.yml"


def test_utc_now_is_whole_seconds_utc() -> None:
    now = utc_now()
    assert now.tzinfo is UTC
    assert now.microsecond == 0
