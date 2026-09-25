"""Deterministic, model-agnostic benchmark metrics."""

import math
import statistics
import unicodedata


def normalize_answer(value):
    """Apply only Unicode compatibility normalization and whitespace cleanup."""
    if value is None:
        return None
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _ratio(numerator, denominator):
    return float(numerator) / denominator if denominator else None


def _is_ground_truth_correct(record):
    student_answer = normalize_answer(record.get("student_answer_gt"))
    correct_answer = normalize_answer(record.get("correct_answer"))
    return student_answer is not None and student_answer == correct_answer


def summarize_latency(predictions):
    values = [
        float(prediction["latency_ms"])
        for prediction in predictions
        if prediction.get("latency_ms") is not None
    ]
    if not values:
        return {"count": 0, "mean_ms": None, "median_ms": None, "p95_ms": None}
    sorted_values = sorted(values)
    p95_index = max(0, int(math.ceil(0.95 * len(sorted_values))) - 1)
    return {
        "count": len(values),
        "mean_ms": float(statistics.mean(values)),
        "median_ms": float(statistics.median(values)),
        "p95_ms": float(sorted_values[p95_index]),
    }


def compute_metrics(ground_truth, predictions):
    """Compute recognition and automated grading metrics.

    Missing predictions count as review-required and as an incorrect exact match.
    Ratio fields are ``None`` when their denominator is zero.
    """
    prediction_by_sample = {}
    for prediction in predictions:
        sample_id = prediction["sample_id"]
        if sample_id in prediction_by_sample:
            raise ValueError("more than one selected prediction for sample_id {!r}".format(sample_id))
        prediction_by_sample[sample_id] = prediction

    known_sample_ids = {record["sample_id"] for record in ground_truth}
    unknown_prediction_ids = set(prediction_by_sample) - known_sample_ids
    if unknown_prediction_ids:
        raise ValueError(
            "predictions reference unknown sample_id(s): {}".format(
                ", ".join(sorted(unknown_prediction_ids))
            )
        )

    total = len(ground_truth)
    exact_matches = 0
    automated = 0
    correct_auto_decisions = 0
    auto_accepts = 0
    false_auto_accepts = 0
    review_required = 0
    missing_predictions = 0

    for record in ground_truth:
        prediction = prediction_by_sample.get(record["sample_id"])
        if prediction is None:
            missing_predictions += 1
            review_required += 1
            continue

        predicted_answer = normalize_answer(prediction.get("normalized_prediction"))
        student_answer = normalize_answer(record.get("student_answer_gt"))
        recognition_matches = (
            predicted_answer is not None
            and student_answer is not None
            and predicted_answer == student_answer
        )
        if recognition_matches:
            exact_matches += 1

        decision_status = prediction["decision_status"]
        if decision_status == "REVIEW_REQUIRED":
            review_required += 1
            continue

        automated += 1
        answer_is_correct = _is_ground_truth_correct(record)
        expected_decision = "AUTO_ACCEPT" if answer_is_correct else "AUTO_WRONG"
        if decision_status == expected_decision:
            correct_auto_decisions += 1
        if decision_status == "AUTO_ACCEPT":
            auto_accepts += 1
            if not recognition_matches:
                false_auto_accepts += 1

    return {
        "total_questions": total,
        "predicted_questions": len(prediction_by_sample),
        "missing_prediction_count": missing_predictions,
        "answer_exact_match": {
            "correct": exact_matches,
            "total": total,
            "rate": _ratio(exact_matches, total),
        },
        "auto_grade_precision": {
            "correct_decisions": correct_auto_decisions,
            "automated_decisions": automated,
            "rate": _ratio(correct_auto_decisions, automated),
        },
        "auto_coverage": {
            "automated_decisions": automated,
            "total": total,
            "rate": _ratio(automated, total),
        },
        "review_rate": {
            "review_required": review_required,
            "total": total,
            "rate": _ratio(review_required, total),
        },
        "false_auto_accept": {
            "false_auto_accepts": false_auto_accepts,
            "auto_accept_decisions": auto_accepts,
            "rate": _ratio(false_auto_accepts, auto_accepts),
        },
        "latency": summarize_latency(predictions),
    }
