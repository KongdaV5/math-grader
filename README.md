# Math Grader Benchmark Foundation

P0-W1 provides model-neutral data contracts, deterministic metrics, a reference-only failure archive, and a small CLI. It does not run OCR or VLM models. The built-in stub emits no answer and routes every question to review, so it can exercise the pipeline without pretending to measure model accuracy.

## Requirements and setup

- Python 3.9 or newer
- Runtime dependency: `jsonschema` for Draft 2020-12 validation
- Development dependency: `pytest`

From the project root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade 'pip>=23.1,<25'
python -m pip install -e '.[dev]'
python -m pytest
```

## Run the empty-dataset smoke example

```sh
python -m benchmark.run \
  --dataset benchmark/dataset/dataset_manifest.example.json \
  --predictor stub \
  --output-dir benchmark/runs/smoke
```

The runner writes `metrics.json`, `predictions.selected.jsonl`, `report.md`, and a reference-only failure archive under the output directory. `benchmark/runs/` is ignored by Git. The default output path is `benchmark/runs/latest`; generated files there are replaced on each run.

## Prepare a dataset

Copy `benchmark/dataset/dataset_manifest.example.json`, update its dataset name and relative paths, then create the referenced UTF-8 Ground Truth JSONL file. Each non-blank line describes one question and must conform to `benchmark/schemas/ground-truth.schema.json`. The manifest, Ground Truth, and Prediction records each carry `schema_version: "0.1"`.

Ground Truth requires a unique `sample_id`, `page_id`, `question_id`, controlled `answer_type`, the student's answer (or `null` for blank), the correct answer, correction flag, and image quality. It requires either `image_ref` or `image`; prefer a relative `image_ref`. Student IDs may be anonymous or omitted. Keep real photos in `benchmark/dataset/raw/`; `.gitignore` excludes them and allows only its README to be tracked.

Prediction JSONL stores one `RecognitionRun` per sample and run. A question can therefore have separate OCR, 4B, and 8B records. `run_id` identifies an inference run; `(sample_id, run_id)` must be unique in a file. If a selected sample has multiple matching records, choose one with `--run-id` rather than combining model attempts.

For example:

```sh
python -m benchmark.run \
  --dataset benchmark/dataset/dataset_manifest.json \
  --predictions benchmark/predictions/ppocr.jsonl \
  --model-name ppocrv6-medium \
  --model-version 'local-build-1' \
  --output-dir benchmark/runs/ppocrv6-medium
```

Manifest paths are resolved relative to the manifest file. Input files are validated strictly; malformed JSONL, schema violations, duplicate IDs, unknown samples, and ambiguous selected runs stop the run and are written to `failures/failures.jsonl` and `failures/index.json`.

## Metric definitions

- **Answer Exact Match**: recognized `normalized_prediction` exactly equals the annotated `student_answer_gt` after Unicode NFKC normalization and whitespace cleanup, divided by all Ground Truth questions. No arithmetic equivalence is inferred.
- **Auto-grade Precision**: correct `AUTO_ACCEPT` / `AUTO_WRONG` decisions divided by all automated decisions. Expected grading is computed deterministically from Ground Truth student answer and correct answer.
- **Auto Coverage**: automated decisions divided by all Ground Truth questions.
- **Review Rate**: explicit `REVIEW_REQUIRED` plus missing predictions divided by all Ground Truth questions.
- **False Auto-Accept**: a `normalized_prediction` that mismatches the Ground Truth student answer but is still marked `AUTO_ACCEPT`, divided by all `AUTO_ACCEPT` decisions.

Each metric stores its numerator and denominator. Undefined ratios (including empty datasets or a zero denominator) are JSON `null`; NaN and Infinity are never emitted. The report marks memory as not measured. Failure records contain IDs and image references, never copied or modified source photos.
