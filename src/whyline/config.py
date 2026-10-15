"""Layered whyline config: built-in defaults < user config < project config (docs/02 section 5).

Command-line flags override the result; each command applies its own flags.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from whyline.errors import CorruptError
from whyline.models import Config
from whyline.store import (
    CONFIG_FILENAME,
    WHYLINE_DIRNAME,
    describe_validation_error,
    ensure_supported_schema,
)

CONFIG_HOME_ENV = "WHYLINE_CONFIG_HOME"
"""Directory holding the user ``config.yml``. Overrides the XDG location; tests set it."""


def user_config_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the user config path.

    ``$WHYLINE_CONFIG_HOME/config.yml``, else ``$XDG_CONFIG_HOME/whyline/config.yml``, else
    ``~/.config/whyline/config.yml``.
    """
    environ = os.environ if env is None else env
    if home := environ.get(CONFIG_HOME_ENV):
        return Path(home) / CONFIG_FILENAME
    if xdg := environ.get("XDG_CONFIG_HOME"):
        return Path(xdg) / "whyline" / CONFIG_FILENAME
    return Path.home() / ".config" / "whyline" / CONFIG_FILENAME


def project_config_path(repo_root: Path) -> Path:
    """Return ``<repo_root>/.whyline/config.yml``."""
    return repo_root / WHYLINE_DIRNAME / CONFIG_FILENAME


def read_config_file(path: Path, *, label: str) -> dict[str, Any]:
    """Return the raw mapping in a config file, or ``{}`` if it does not exist.

    The file is validated on its own so an error names the file it came from.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as exc:
        raise CorruptError(f"Cannot read {label} {path}: {exc}.") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        problem = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        raise CorruptError(
            f"{label} {path} is not valid YAML ({problem}).", hint="Fix the file."
        ) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise CorruptError(f"{label} {path} is not a YAML mapping.", hint="Fix the file.")
    ensure_supported_schema(data.get("schema_version"), f"{label} {path}")
    try:
        Config.model_validate(data)
    except ValidationError as exc:
        raise CorruptError(
            f"{label} {path} failed validation: {describe_validation_error(exc)}.",
            hint="Fix the file, or run `whyline init --force` to reset the project config.",
        ) from exc
    return data


def load_config(repo_root: Path, *, user_path: Path | None = None) -> Config:
    """Return the effective config for ``repo_root``: defaults < user < project."""
    user = read_config_file(user_path or user_config_path(), label="User config")
    project = read_config_file(project_config_path(repo_root), label="Project config")
    merged = _deep_merge(_deep_merge(Config().model_dump(mode="json"), user), project)
    return Config.model_validate(merged)


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge mappings recursively. Lists and scalars in ``override`` replace those in ``base``."""
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged
