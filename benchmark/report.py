"""Markdown report rendering from a deterministic result payload."""

from pathlib import Path


def _rate(value):
    return "N/A" if value is None else "{:.2f}%".format(value * 100.0)


def _latency(value):
    if value["count"] == 0:
        return "Not measured"
    return "mean {:.2f} ms; median {:.2f} ms; p95 {:.2f} ms".format(
        value["mean_ms"], value["median_ms"], value["p95_ms"]
    )


def render_report(result, template_path=None):
    if template_path is None:
        template_path = Path(__file__).parent / "reports" / "BENCHMARK_REPORT_TEMPLATE.md"
    template = Path(template_path).read_text(encoding="utf-8")
    metrics = result["metrics"]
    failures = result["failure_taxonomy"]
    model = result["model"]
    replacements = {
        "$dataset_name": result["dataset"]["dataset_name"],
        "$sample_count": str(result["dataset"]["sample_count"]),
        "$prediction_count": str(result["prediction_count"]),
        "$missing_prediction_count": str(metrics["missing_prediction_count"]),
        "$selected_model": model["display"],
        "$exact_match": _rate(metrics["answer_exact_match"]["rate"]),
        "$precision": _rate(metrics["auto_grade_precision"]["rate"]),
        "$coverage": _rate(metrics["auto_coverage"]["rate"]),
        "$review_rate": _rate(metrics["review_rate"]["rate"]),
        "$false_auto_accept": _rate(metrics["false_auto_accept"]["rate"]),
        "$latency": _latency(metrics["latency"]),
        "$memory": result["memory"]["note"],
        "$failure_taxonomy": ", ".join(
            "{}: {}".format(category, count)
            for category, count in failures.items()
        ),
        "$decision": "Foundation run only; model readiness is not evaluated in P0-W1.",
    }
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    return rendered
