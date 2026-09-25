"""Explicit non-model predictors for exercising the benchmark pipeline."""


class ReviewOnlyStubPredictor:
    """A safe stub that emits no answer and routes every sample to review."""

    model_name = "stub-review-only"
    model_version = "0.1"
    run_id = "stub-review-only-0.1"

    def predict(self, ground_truth_record):
        return {
            "schema_version": "0.1",
            "run_id": self.run_id,
            "sample_id": ground_truth_record["sample_id"],
            "model_name": self.model_name,
            "model_version": self.model_version,
            "raw_prediction": None,
            "normalized_prediction": None,
            "model_confidence": None,
            "decision_status": "REVIEW_REQUIRED",
            "decision_confidence": None,
            "latency_ms": None,
            "error": None,
        }
