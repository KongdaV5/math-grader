"""Error types shared by the benchmark readers and runner."""


class BenchmarkError(Exception):
    """Base class for errors that should be shown clearly by the CLI."""


class InputDataError(BenchmarkError):
    """A malformed input record with enough context for a failure archive."""

    def __init__(
        self,
        message,
        *,
        source=None,
        line_number=None,
        category="schema_error",
        record=None,
    ):
        super().__init__(message)
        self.source = str(source) if source is not None else None
        self.line_number = line_number
        self.category = category
        self.record = record if isinstance(record, dict) else {}

    def as_failure(self):
        return {
            "category": self.category,
            "sample_id": self.record.get("sample_id"),
            "question_id": self.record.get("question_id"),
            "image_ref": self.record.get("image_ref", self.record.get("image")),
            "source": self.source,
            "line_number": self.line_number,
            "reason": str(self),
        }
