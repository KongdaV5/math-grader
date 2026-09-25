"""Small, synthetic fixtures used only by the benchmark tests."""

import json
from pathlib import Path


def ground_truth(
    sample_id="sample-1",
    *,
    student_answer="42",
    correct_answer="42",
    answer_type="integer",
):
    return {
        "schema_version": "0.1",
        "sample_id": sample_id,
        "image_ref": "raw/example-page.jpg",
        "student_id": "anonymous-test-student",
        "page_id": "page-1",
        "question_id": "q-1",
        "answer_type": answer_type,
        "student_answer_gt": student_answer,
        "correct_answer": correct_answer,
        "has_correction": False,
        "image_quality": "normal",
        "metadata": {"synthetic_fixture": True},
    }


def prediction(
    sample_id="sample-1",
    *,
    answer="42",
    decision_status="AUTO_ACCEPT",
    model_name="test-model",
    model_version="1",
    run_id="run-1",
    error=None,
    latency_ms=10,
):
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "sample_id": sample_id,
        "model_name": model_name,
        "model_version": model_version,
        "raw_prediction": answer,
        "normalized_prediction": answer,
        "model_confidence": 0.9,
        "decision_status": decision_status,
        "decision_confidence": 0.9,
        "latency_ms": latency_ms,
        "error": error,
    }


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def make_dataset(directory, records):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_jsonl(directory / "ground_truth.jsonl", records)
    (directory / "raw").mkdir(exist_ok=True)
    manifest = {
        "schema_version": "0.1",
        "dataset_name": "synthetic-test-dataset",
        "samples_source": "raw",
        "ground_truth": "ground_truth.jsonl",
    }
    (directory / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return directory / "dataset_manifest.json"
