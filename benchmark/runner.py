"""Dataset loading, prediction selection, evaluation, and artifact writing."""

from pathlib import Path

from .errors import InputDataError
from .failures import FAILURE_CATEGORIES, FailureArchive
from .io import (
    load_dataset_manifest,
    load_ground_truth,
    load_predictions,
    resolve_manifest_path,
    write_json,
    write_jsonl,
)
from .metrics import compute_metrics, normalize_answer
from .predictors import ReviewOnlyStubPredictor
from .report import render_report
from .schemas import validate_payload


def _selected_model_name(predictions, selector):
    identities = sorted(
        {(record["model_name"], record["model_version"]) for record in predictions}
    )
    if len(identities) > 1:
        raise InputDataError(
            "selected predictions contain multiple model/version pairs; specify a model and version",
            category="invalid_prediction",
        )
    if identities:
        name, version = identities[0]
        run_ids = sorted({record["run_id"] for record in predictions})
        return {
            "name": name,
            "version": version,
            "run_ids": run_ids,
            "display": "{}@{}".format(name, version),
        }
    return {
        "name": selector.get("model_name"),
        "version": selector.get("model_version"),
        "run_ids": [],
        "display": "no prediction rows selected",
    }


def _select_predictions(ground_truth, predictions, selector, archive):
    known_ids = {record["sample_id"] for record in ground_truth}
    for prediction in predictions:
        if prediction["sample_id"] not in known_ids:
            error = InputDataError(
                "prediction refers to unknown sample_id {!r}".format(prediction["sample_id"]),
                category="invalid_prediction",
                record=prediction,
            )
            archive.extend_input_error(error)
            raise error

    filtered = [
        prediction
        for prediction in predictions
        if (selector.get("model_name") is None or prediction["model_name"] == selector["model_name"])
        and (selector.get("model_version") is None or prediction["model_version"] == selector["model_version"])
        and (selector.get("run_id") is None or prediction["run_id"] == selector["run_id"])
    ]
    by_sample = {}
    for prediction in filtered:
        by_sample.setdefault(prediction["sample_id"], []).append(prediction)

    ambiguous = [sample_id for sample_id, rows in by_sample.items() if len(rows) > 1]
    if ambiguous:
        sample_id = sorted(ambiguous)[0]
        rows = by_sample[sample_id]
        error = InputDataError(
            "multiple prediction records selected for sample_id {!r}; specify --model-version or --run-id".format(sample_id),
            category="invalid_prediction",
            record=rows[0],
        )
        archive.extend_input_error(error)
        raise error

    selected = [by_sample[record["sample_id"]][0] for record in ground_truth if record["sample_id"] in by_sample]
    return selected


def _archive_evaluation_failures(ground_truth, predictions, archive):
    predictions_by_id = {prediction["sample_id"]: prediction for prediction in predictions}
    for record in ground_truth:
        prediction = predictions_by_id.get(record["sample_id"])
        common = {
            "sample_id": record["sample_id"],
            "question_id": record["question_id"],
            "image_ref": record.get("image_ref", record.get("image")),
        }
        if prediction is None:
            archive.add(
                "review_required",
                **common,
                reason="MISSING_PREDICTION",
            )
            continue

        if prediction.get("error") is not None:
            archive.add(
                "invalid_prediction",
                **common,
                model_name=prediction["model_name"],
                model_version=prediction["model_version"],
                error=prediction["error"],
            )

        predicted_answer = normalize_answer(prediction.get("normalized_prediction"))
        expected_answer = normalize_answer(record.get("student_answer_gt"))
        if predicted_answer is not None and expected_answer is not None and predicted_answer != expected_answer:
            archive.add(
                "recognition_mismatch",
                **common,
                model_name=prediction["model_name"],
                model_version=prediction["model_version"],
                prediction=prediction.get("normalized_prediction"),
                expected=record.get("student_answer_gt"),
            )

        if prediction["decision_status"] == "REVIEW_REQUIRED":
            archive.add(
                "review_required",
                **common,
                model_name=prediction["model_name"],
                model_version=prediction["model_version"],
                reason="DECISION_REQUIRES_REVIEW",
            )
        elif prediction["decision_status"] == "AUTO_ACCEPT":
            student_answer = normalize_answer(record.get("student_answer_gt"))
            if predicted_answer is None or student_answer is None or predicted_answer != student_answer:
                archive.add(
                    "false_auto_accept",
                    **common,
                    model_name=prediction["model_name"],
                    model_version=prediction["model_version"],
                    prediction=prediction.get("normalized_prediction"),
                    student_answer_gt=record.get("student_answer_gt"),
                    correct_answer=record.get("correct_answer"),
                )


def run_benchmark(
    dataset,
    *,
    output_dir,
    predictions_path=None,
    selector=None,
    predictor=None,
):
    """Run an evaluation and write metrics, selected predictions, failures, and report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = FailureArchive(output_dir)
    selector = selector or {}
    try:
        manifest, manifest_path = load_dataset_manifest(dataset)
        ground_truth_path = resolve_manifest_path(manifest_path, manifest["ground_truth"])
        ground_truth = load_ground_truth(ground_truth_path)

        if predictions_path is None:
            predictor = predictor or ReviewOnlyStubPredictor()
            predictions = [predictor.predict(record) for record in ground_truth]
            for prediction in predictions:
                validate_payload(prediction, "prediction")
        else:
            predictions = load_predictions(predictions_path)

        selected_predictions = _select_predictions(ground_truth, predictions, selector, archive)
        model = _selected_model_name(selected_predictions, selector)
        if not selected_predictions and predictions_path is None:
            model = {
                "name": predictor.model_name,
                "version": predictor.model_version,
                "run_ids": [predictor.run_id],
                "display": "{}@{} (stub)".format(predictor.model_name, predictor.model_version),
            }
        _archive_evaluation_failures(ground_truth, selected_predictions, archive)
        metrics = compute_metrics(ground_truth, selected_predictions)

        failure_taxonomy = {category: 0 for category in FAILURE_CATEGORIES}
        for failure in archive.records:
            failure_taxonomy[failure["category"]] += 1

        result = {
            "schema_version": "0.1",
            "dataset": {
                "dataset_name": manifest["dataset_name"],
                "manifest": manifest_path.name,
                "ground_truth": manifest["ground_truth"],
                "samples_source": manifest["samples_source"],
                "sample_count": len(ground_truth),
            },
            "model": model,
            "prediction_count": len(selected_predictions),
            "metrics": metrics,
            "failure_taxonomy": failure_taxonomy,
            "memory": {"peak_mb": None, "note": "Not measured by P0-W1."},
        }
        archive.write()
        write_json(output_dir / "metrics.json", result)
        write_jsonl(output_dir / "predictions.selected.jsonl", selected_predictions)
        report = render_report(result)
        with (output_dir / "report.md").open("w", encoding="utf-8", newline="\n") as report_file:
            report_file.write(report)
        return result
    except InputDataError as error:
        if not any(
            record.get("source") == error.source
            and record.get("line_number") == error.line_number
            and record.get("reason") == str(error)
            for record in archive.records
        ):
            archive.extend_input_error(error)
        archive.write()
        raise
