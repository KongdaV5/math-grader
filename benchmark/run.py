"""Command-line entry point: ``python -m benchmark.run``."""

import argparse
import json
import sys
from pathlib import Path

from .errors import BenchmarkError
from .predictors import ReviewOnlyStubPredictor
from .runner import run_benchmark


def build_parser():
    parser = argparse.ArgumentParser(description="Run the Math Grader benchmark foundation.")
    parser.add_argument(
        "--dataset",
        required=True,
        help="dataset manifest JSON path or directory containing dataset_manifest.json",
    )
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--predictions", help="prediction/RecognitionRun JSONL file")
    source_group.add_argument("--predictor", choices=["stub"], help="built-in review-only stub")
    parser.add_argument(
        "--model-name",
        help="select this model from a multi-model predictions file",
    )
    parser.add_argument("--model-version", help="select this model version")
    parser.add_argument("--run-id", help="select this prediction run when more than one matches")
    parser.add_argument(
        "--output-dir",
        default="benchmark/runs/latest",
        help="artifact directory (default: benchmark/runs/latest; generated files are replaced)",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.predictions is None and any(
        value is not None for value in (args.model_name, args.model_version, args.run_id)
    ):
        parser.error("model selectors can only be used with --predictions")

    predictor = ReviewOnlyStubPredictor() if args.predictions is None else None
    if args.predictor == "stub":
        predictor = ReviewOnlyStubPredictor()
    selector = {
        "model_name": args.model_name,
        "model_version": args.model_version,
        "run_id": args.run_id,
    }
    try:
        result = run_benchmark(
            args.dataset,
            output_dir=args.output_dir,
            predictions_path=args.predictions,
            selector=selector,
            predictor=predictor,
        )
    except BenchmarkError as error:
        print("benchmark error: {}".format(error), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "dataset": result["dataset"]["dataset_name"],
                "samples": result["dataset"]["sample_count"],
                "model": result["model"]["display"],
                "metrics_file": str(Path(args.output_dir) / "metrics.json"),
                "report_file": str(Path(args.output_dir) / "report.md"),
                "review_rate": result["metrics"]["review_rate"]["rate"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
