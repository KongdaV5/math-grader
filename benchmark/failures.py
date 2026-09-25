"""Reference-only failure archive for benchmark runs."""

from collections import Counter
from pathlib import Path

from .io import write_json, write_jsonl


FAILURE_CATEGORIES = (
    "recognition_mismatch",
    "false_auto_accept",
    "review_required",
    "invalid_prediction",
    "schema_error",
)


class FailureArchive:
    """Collect failure references without copying or modifying source images."""

    def __init__(self, output_dir):
        self.root = Path(output_dir) / "failures"
        self.records = []

    def add(self, category, **details):
        if category not in FAILURE_CATEGORIES:
            raise ValueError("unknown failure category {!r}".format(category))
        record = {"category": category}
        record.update(details)
        # Keep every index row traceable while omitting unavailable values.
        self.records.append(
            {
                key: value
                for key, value in record.items()
                if value is not None
            }
        )

    def extend_input_error(self, error):
        details = error.as_failure()
        details.pop("category", None)
        self.add(error.category, **details)

    def write(self):
        self.root.mkdir(parents=True, exist_ok=True)
        write_jsonl(self.root / "failures.jsonl", self.records)
        counts = Counter(record["category"] for record in self.records)
        write_json(
            self.root / "index.json",
            {
                "categories": {
                    category: counts.get(category, 0) for category in FAILURE_CATEGORIES
                },
                "total_failures": len(self.records),
                "records_file": "failures.jsonl",
            },
        )
