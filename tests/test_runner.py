import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmark.errors import InputDataError
from benchmark.io import write_jsonl
from benchmark.runner import run_benchmark
from tests.helpers import ground_truth, prediction, make_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


def test_empty_dataset_stub_smoke_writes_all_artifacts(tmp_path):
    manifest = PROJECT_ROOT / "benchmark/dataset/dataset_manifest.example.json"
    output_dir = tmp_path / "empty-smoke"

    result = run_benchmark(manifest, output_dir=output_dir)

    assert result["dataset"]["sample_count"] == 0
    assert result["model"]["name"] == "stub-review-only"
    assert result["metrics"]["answer_exact_match"]["rate"] is None
    assert result["metrics"]["review_rate"]["rate"] is None
    assert (output_dir / "metrics.json").is_file()
    assert (output_dir / "predictions.selected.jsonl").is_file()
    assert (output_dir / "report.md").is_file()
    assert (output_dir / "failures/failures.jsonl").is_file()
    assert "$dataset_name" not in (output_dir / "report.md").read_text(encoding="utf-8")


def test_review_only_stub_is_conservative_and_archived(tmp_path):
    manifest = make_dataset(tmp_path / "dataset", [ground_truth()])
    output_dir = tmp_path / "run"

    result = run_benchmark(manifest, output_dir=output_dir)

    assert result["model"]["name"] == "stub-review-only"
    assert result["metrics"]["auto_coverage"]["rate"] == 0.0
    assert result["metrics"]["review_rate"]["rate"] == 1.0
    failures = read_jsonl(output_dir / "failures/failures.jsonl")
    assert failures[0]["category"] == "review_required"
    assert failures[0]["sample_id"] == "sample-1"


def test_missing_prediction_counts_as_review_and_failure_reference(tmp_path):
    manifest = make_dataset(
        tmp_path / "dataset",
        [ground_truth("s1"), ground_truth("s2", student_answer="5", correct_answer="5")],
    )
    predictions_path = tmp_path / "predictions.jsonl"
    write_jsonl(predictions_path, [prediction("s1")])
    output_dir = tmp_path / "run"

    result = run_benchmark(
        manifest,
        output_dir=output_dir,
        predictions_path=predictions_path,
        selector={"model_name": "test-model", "model_version": "1"},
    )

    assert result["metrics"]["missing_prediction_count"] == 1
    assert result["metrics"]["review_rate"]["rate"] == 0.5
    failures = read_jsonl(output_dir / "failures/failures.jsonl")
    assert any(item["sample_id"] == "s2" and item["reason"] == "MISSING_PREDICTION" for item in failures)


def test_false_auto_accept_and_recognition_mismatch_are_both_archived(tmp_path):
    manifest = make_dataset(
        tmp_path / "dataset",
        [ground_truth("s1", student_answer="3", correct_answer="4")],
    )
    predictions_path = tmp_path / "predictions.jsonl"
    write_jsonl(predictions_path, [prediction("s1", answer="8")])
    output_dir = tmp_path / "run"

    result = run_benchmark(
        manifest,
        output_dir=output_dir,
        predictions_path=predictions_path,
    )

    assert result["metrics"]["false_auto_accept"]["rate"] == 1.0
    failures = read_jsonl(output_dir / "failures/failures.jsonl")
    categories = {item["category"] for item in failures}
    assert categories == {"recognition_mismatch", "false_auto_accept"}
    assert all(item.get("image_ref") == "raw/example-page.jpg" for item in failures)


def test_malformed_ground_truth_is_archived_then_fails_closed(tmp_path):
    manifest = make_dataset(tmp_path / "dataset", [])
    ground_truth_path = tmp_path / "dataset/ground_truth.jsonl"
    ground_truth_path.write_text("{not-json}\n", encoding="utf-8")
    output_dir = tmp_path / "run"

    with pytest.raises(InputDataError, match="malformed JSON"):
        run_benchmark(manifest, output_dir=output_dir)

    failures = read_jsonl(output_dir / "failures/failures.jsonl")
    assert failures[0]["category"] == "schema_error"
    assert failures[0]["line_number"] == 1


def test_unknown_prediction_sample_is_archived_and_rejected(tmp_path):
    manifest = make_dataset(tmp_path / "dataset", [ground_truth()])
    predictions_path = tmp_path / "predictions.jsonl"
    write_jsonl(predictions_path, [prediction("not-in-dataset")])
    output_dir = tmp_path / "run"

    with pytest.raises(InputDataError, match="unknown sample_id"):
        run_benchmark(manifest, output_dir=output_dir, predictions_path=predictions_path)

    failures = read_jsonl(output_dir / "failures/failures.jsonl")
    assert failures[0]["category"] == "invalid_prediction"
    assert failures[0]["sample_id"] == "not-in-dataset"


def test_cli_runner_smoke_command(tmp_path):
    manifest = make_dataset(tmp_path / "dataset", [ground_truth()])
    output_dir = tmp_path / "cli-smoke"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmark.run",
            "--dataset",
            str(manifest),
            "--predictor",
            "stub",
            "--output-dir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output["dataset"] == "synthetic-test-dataset"
    assert output["samples"] == 1
    assert output["review_rate"] == 1.0
    assert Path(output["metrics_file"]).is_file()


def test_multiple_recognition_runs_require_an_explicit_selection(tmp_path):
    manifest = make_dataset(tmp_path / "dataset", [ground_truth()])
    predictions_path = tmp_path / "predictions.jsonl"
    write_jsonl(
        predictions_path,
        [
            prediction(run_id="ocr-run", model_name="ocr"),
            prediction(run_id="vlm-run", model_name="vlm"),
        ],
    )

    with pytest.raises(InputDataError, match="multiple prediction records selected"):
        run_benchmark(
            manifest,
            output_dir=tmp_path / "ambiguous",
            predictions_path=predictions_path,
        )

    result = run_benchmark(
        manifest,
        output_dir=tmp_path / "selected",
        predictions_path=predictions_path,
        selector={"model_name": "vlm"},
    )
    assert result["model"]["name"] == "vlm"
