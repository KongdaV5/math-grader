"""Strict readers and writers for manifests and JSON Lines data."""

import json
from pathlib import Path

from .errors import InputDataError
from .schemas import validate_payload


def _read_json(path, schema_name):
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as json_file:
            payload = json.load(json_file)
    except FileNotFoundError as exc:
        raise InputDataError(
            "file does not exist",
            source=path,
            category="schema_error",
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError(
            "could not read JSON: {}".format(exc),
            source=path,
            category="schema_error",
        ) from exc
    return validate_payload(payload, schema_name, source=path)


def load_dataset_manifest(path):
    """Load a manifest file, or a dataset directory containing the default name."""
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "dataset_manifest.json"
    manifest = _read_json(manifest_path, "dataset_manifest")
    return manifest, manifest_path.resolve()


def resolve_manifest_path(manifest_path, referenced_path):
    """Resolve a manifest path relative to the manifest's directory."""
    referenced_path = Path(referenced_path)
    if not referenced_path.is_absolute():
        referenced_path = Path(manifest_path).parent / referenced_path
    return referenced_path.resolve()


def load_jsonl(path, schema_name, *, unique_key=None, duplicate_category=None):
    """Read and validate JSONL with line-specific errors and optional uniqueness."""
    path = Path(path)
    try:
        jsonl_file = path.open("r", encoding="utf-8")
    except FileNotFoundError as exc:
        raise InputDataError(
            "file does not exist",
            source=path,
            category="schema_error",
        ) from exc
    except OSError as exc:
        raise InputDataError(
            "could not open JSONL: {}".format(exc),
            source=path,
            category="schema_error",
        ) from exc

    records = []
    seen = set()
    try:
        with jsonl_file:
            for line_number, line in enumerate(jsonl_file, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise InputDataError(
                        "malformed JSON on line {}: {}".format(line_number, exc.msg),
                        source=path,
                        line_number=line_number,
                        category="schema_error",
                    ) from exc
                validate_payload(
                    record,
                    schema_name,
                    source=path,
                    line_number=line_number,
                )
                if unique_key is not None:
                    key = unique_key(record)
                    if key in seen:
                        raise InputDataError(
                            "duplicate record key {!r} on line {}".format(key, line_number),
                            source=path,
                            line_number=line_number,
                            category=duplicate_category or "schema_error",
                            record=record,
                        )
                    seen.add(key)
                records.append(record)
    except UnicodeError as exc:
        raise InputDataError(
            "JSONL file is not valid UTF-8: {}".format(exc),
            source=path,
            category="schema_error",
        ) from exc
    return records


def load_ground_truth(path):
    return load_jsonl(
        path,
        "ground_truth",
        unique_key=lambda record: record["sample_id"],
        duplicate_category="schema_error",
    )


def load_predictions(path):
    return load_jsonl(
        path,
        "prediction",
        unique_key=lambda record: (record["sample_id"], record["run_id"]),
        duplicate_category="invalid_prediction",
    )


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as json_file:
        json.dump(payload, json_file, ensure_ascii=False, indent=2, allow_nan=False)
        json_file.write("\n")


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as jsonl_file:
        for record in records:
            jsonl_file.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            )
            jsonl_file.write("\n")
