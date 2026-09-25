from benchmark.metrics import compute_metrics
from tests.helpers import ground_truth, prediction


def test_metrics_cover_mixed_auto_review_missing_and_false_auto_accept():
    ground_truth_records = [
        ground_truth("s1", student_answer="7", correct_answer="7"),
        ground_truth("s2", student_answer="3", correct_answer="4"),
        ground_truth("s3", student_answer="2", correct_answer="5"),
        ground_truth("s4", student_answer="9", correct_answer="9"),
        ground_truth("s5", student_answer="1", correct_answer="2"),
    ]
    predictions = [
        prediction("s1", answer="7", decision_status="AUTO_ACCEPT"),
        prediction("s2", answer="3", decision_status="AUTO_WRONG", run_id="run-2"),
        prediction("s3", answer="2", decision_status="AUTO_ACCEPT", run_id="run-3"),
        prediction("s5", answer="1", decision_status="REVIEW_REQUIRED", run_id="run-5"),
    ]

    metrics = compute_metrics(ground_truth_records, predictions)

    assert metrics["answer_exact_match"] == {"correct": 4, "total": 5, "rate": 0.8}
    assert metrics["auto_grade_precision"] == {
        "correct_decisions": 2,
        "automated_decisions": 3,
        "rate": 2 / 3,
    }
    assert metrics["auto_coverage"] == {"automated_decisions": 3, "total": 5, "rate": 0.6}
    assert metrics["review_rate"] == {"review_required": 2, "total": 5, "rate": 0.4}
    assert metrics["missing_prediction_count"] == 1
    assert metrics["false_auto_accept"] == {
        "false_auto_accepts": 0,
        "auto_accept_decisions": 2,
        "rate": 0.0,
    }


def test_full_auto_dataset_has_defined_precision_coverage_and_zero_review():
    records = [ground_truth("s1"), ground_truth("s2", student_answer="5", correct_answer="5")]
    predictions = [
        prediction("s1"),
        prediction("s2", answer="5", run_id="run-2"),
    ]

    metrics = compute_metrics(records, predictions)

    assert metrics["answer_exact_match"]["rate"] == 1.0
    assert metrics["auto_grade_precision"]["rate"] == 1.0
    assert metrics["auto_coverage"]["rate"] == 1.0
    assert metrics["review_rate"]["rate"] == 0.0
    assert metrics["false_auto_accept"]["rate"] == 0.0


def test_full_review_has_zero_coverage_and_undefined_precision():
    records = [ground_truth("s1"), ground_truth("s2")]
    predictions = [
        prediction("s1", answer=None, decision_status="REVIEW_REQUIRED"),
        prediction("s2", answer=None, decision_status="REVIEW_REQUIRED", run_id="run-2"),
    ]

    metrics = compute_metrics(records, predictions)

    assert metrics["auto_grade_precision"]["rate"] is None
    assert metrics["auto_coverage"]["rate"] == 0.0
    assert metrics["review_rate"]["rate"] == 1.0
    assert metrics["false_auto_accept"]["rate"] is None


def test_empty_dataset_and_zero_denominators_use_null_not_non_finite_values():
    metrics = compute_metrics([], [])

    assert metrics["answer_exact_match"]["rate"] is None
    assert metrics["auto_grade_precision"]["rate"] is None
    assert metrics["auto_coverage"]["rate"] is None
    assert metrics["review_rate"]["rate"] is None
    assert metrics["false_auto_accept"]["rate"] is None
    assert metrics["latency"]["mean_ms"] is None


def test_answer_exact_match_only_cleans_unicode_and_whitespace():
    records = [ground_truth("s1", student_answer="１２  3", correct_answer="１２  3")]
    predictions = [prediction("s1", answer="12 3")]
    assert compute_metrics(records, predictions)["answer_exact_match"]["rate"] == 1.0


def test_numeric_equivalence_is_not_inferred():
    records = [ground_truth("s1", student_answer="0.5", correct_answer="0.5")]
    predictions = [prediction("s1", answer="1/2")]
    assert compute_metrics(records, predictions)["answer_exact_match"]["rate"] == 0.0


def test_false_auto_accept_counts_recognition_mismatch_even_for_correct_student_answer():
    records = [ground_truth("s1", student_answer="4", correct_answer="4")]
    predictions = [prediction("s1", answer="8", decision_status="AUTO_ACCEPT")]

    metrics = compute_metrics(records, predictions)

    assert metrics["auto_grade_precision"]["rate"] == 1.0
    assert metrics["false_auto_accept"]["false_auto_accepts"] == 1
    assert metrics["false_auto_accept"]["rate"] == 1.0
