"""The committed JSON Schema must match the model and accept the documented record."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from intentline.cli import app
from intentline.models import Record, record_json_schema, render_record_json_schema
from tests.conftest import doc_yaml_block, record_data

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "schema" / "record.schema.json"
REGENERATE = "uv run intentline schema > schema/record.schema.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(COMMITTED.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _doc_example() -> dict[str, Any]:
    data = yaml.safe_load(doc_yaml_block("## 1. Record schema"))
    return Record.model_validate(data).model_dump(mode="json")


def test_committed_schema_matches_model() -> None:
    committed = COMMITTED.read_text(encoding="utf-8")
    assert committed == render_record_json_schema(), (
        f"schema/record.schema.json is out of date. Regenerate it with: {REGENERATE}"
    )


def test_cli_prints_the_committed_schema() -> None:
    result = CliRunner().invoke(app, ["schema"])
    assert result.exit_code == 0
    assert result.stdout == COMMITTED.read_text(encoding="utf-8")


def test_schema_declares_dialect_and_forbids_unknown_keys() -> None:
    schema = record_json_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert all(d["additionalProperties"] is False for d in schema["$defs"].values())
    assert set(schema["required"]) >= {"schema_version", "id", "status", "goal", "links"}


def test_doc_example_validates_against_committed_schema(validator: Draft202012Validator) -> None:
    validator.validate(_doc_example())


def test_generated_record_validates_against_committed_schema(
    validator: Draft202012Validator,
) -> None:
    validator.validate(Record.model_validate(record_data(7)).model_dump(mode="json"))


@pytest.mark.parametrize(
    "change",
    [
        {"status": "confirmed"},
        {"unknown": 1},
        {"schema_version": 2},
        {"links": []},
        {"goal": ""},
    ],
)
def test_committed_schema_rejects_invalid_records(
    validator: Draft202012Validator, change: dict[str, Any]
) -> None:
    data = _doc_example()
    data.update(change)
    assert not validator.is_valid(data)
