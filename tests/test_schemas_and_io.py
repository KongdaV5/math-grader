import json

import pytest

from benchmark.errors import InputDataError
from benchmark.io import load_ground_truth, load_predictions
from benchmark.schemas import load_schema, validate_payload
from tests.helpers import ground_truth, prediction, write_jsonl


def test_all_versioned_schemas_are_valid_draft_2020_12():
    for schema_name in ("dataset_manifest", "ground_truth", "prediction"):
        assert load_schema(schema_name)["$schema"].endswith("2020-12/schema")


def test_ground_truth_schema_accepts_image_ref_and_anonymous_student():
    record = ground_truth()
    record.pop("student_id")
    assert validate_payload(record, "ground_truth") is record


@pytest.mark.parametrize(
    "mutator",
    [
        lambda record: record.pop("sample_id"),
        lambda record: record.update(answer_type="handwriting_guess"),
        lambda record: record.update(has_correction="false"),
        lambda record: record.pop("image_ref"),
    ],
)
def test_ground_truth_rejects_missing_fields_and_invalid_types(mutator):
    record = ground_truth()
    mutator(record)
    with pytest.raises(InputDataError):
        validate_payload(record, "ground_truth")


def test_prediction_schema_allows_multiple_recognition_runs_per_question(tmp_path):
    path = tmp_path / "predictions.jsonl"
    write_jsonl(
        path,
        [
            prediction(run_id="ocr-1", model_name="ocr"),
            prediction(run_id="vlm-1", model_name="vlm"),
        ],
    )
    loaded = load_predictions(path)
    assert len(loaded) == 2


def test_prediction_error_must_be_routed_to_review():
    record = prediction(
        answer=None,
        decision_status="AUTO_ACCEPT",
        error={"code": "MODEL_TIMEOUT", "message": "timed out"},
    )
    with pytest.raises(InputDataError):
        validate_payload(record, "prediction")


def test_jsonl_reader_reports_malformed_line_number(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text(json.dumps(ground_truth()) + "\n{not json}\n", encoding="utf-8")
    with pytest.raises(InputDataError, match="line 2") as error:
        load_ground_truth(path)
    assert error.value.line_number == 2
    assert error.value.category == "schema_error"


def test_jsonl_reader_reports_non_utf8_data(tmp_path):
    path = tmp_path / "not-utf8.jsonl"
    path.write_bytes(b"\xff\xfe")

    with pytest.raises(InputDataError, match="not valid UTF-8"):
        load_ground_truth(path)


def test_ground_truth_reader_rejects_duplicate_sample_ids(tmp_path):
    path = tmp_path / "duplicate.jsonl"
    write_jsonl(path, [ground_truth(), ground_truth()])
    with pytest.raises(InputDataError, match="duplicate record key") as error:
        load_ground_truth(path)
    assert error.value.line_number == 2


def test_prediction_reader_rejects_duplicate_sample_and_run_id(tmp_path):
    path = tmp_path / "duplicate-predictions.jsonl"
    write_jsonl(path, [prediction(), prediction()])
    with pytest.raises(InputDataError, match="duplicate record key") as error:
        load_predictions(path)
    assert error.value.category == "invalid_prediction"


def test_prediction_reader_allows_same_sample_for_distinct_run_ids(tmp_path):
    path = tmp_path / "multi-run.jsonl"
    write_jsonl(path, [prediction(run_id="ocr"), prediction(run_id="vlm")])
    assert len(load_predictions(path)) == 2
