"""Versioned JSON Schema validation for benchmark input records."""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import InputDataError


_SCHEMA_FILES = {
    "dataset_manifest": "dataset-manifest.schema.json",
    "ground_truth": "ground-truth.schema.json",
    "prediction": "prediction.schema.json",
}


@lru_cache(maxsize=None)
def load_schema(schema_name):
    """Load and meta-validate one of the packaged Draft 2020-12 schemas."""
    try:
        filename = _SCHEMA_FILES[schema_name]
    except KeyError as exc:
        raise ValueError("unknown schema {!r}".format(schema_name)) from exc
    schema_path = Path(__file__).parent / "schemas" / filename
    with schema_path.open("r", encoding="utf-8") as schema_file:
        schema = json.load(schema_file)
    Draft202012Validator.check_schema(schema)
    return schema


def validate_payload(payload, schema_name, *, source=None, line_number=None):
    """Return a payload if valid, otherwise raise a contextual input error."""
    validator = Draft202012Validator(load_schema(schema_name))
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (list(map(str, error.absolute_path)), error.message),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise InputDataError(
            "{}: {}".format(location, error.message),
            source=source,
            line_number=line_number,
            category="schema_error" if schema_name != "prediction" else "invalid_prediction",
            record=payload,
        )
    return payload
