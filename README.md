# Math Grader — Local Homework Capture and Grading

Math Grader is a local-first macOS desktop app for collecting photographed homework, recognizing answers, grading deterministically, and sending uncertain results to teacher review. The current product UI includes the Submission Workspace, new-exam analysis, answer-key confirmation, Assignment template reuse, model center, and human review. P0 benchmark tooling remains in the repository but is not a model-quality claim.

## Use the desktop app

Open **Math Grader.app** from Finder. The app includes its own Python runtime and starts its local service automatically; ordinary use does not require installing Python, opening Terminal, activating a virtual environment, or running a model server.

Recognition models are managed from **模型中心** and are stored separately from the app. They are not loaded or downloaded at app startup. App data and models remain in `~/Library/Application Support/MathGrader/` if the app is replaced or deleted.

The current local app target is Apple Silicon with macOS 15.0 or newer. See [the user guide](docs/USER_GUIDE.md) for ordinary use and [the macOS build guide](docs/development/BUILD_MACOS.md) for developer packaging.

## Developer setup

Packaging the standalone app uses the pinned CPython 3.12.14 runtime, `uv.lock`, Node/npm, Rust/Cargo, and Xcode Command Line Tools. From the repository root, the complete build and local install command is:

```sh
./scripts/build_macos_app.sh
```

The Tauri dev server, browser demo, service CLI, and test commands remain developer tools. They can use a developer Python environment; that path is separate from the installed production app runtime. See [BUILD_MACOS.md](docs/development/BUILD_MACOS.md) for requirements and details.

For a browser demo during development:

```sh
cd desktop
npm run demo:dev
```

The demo uses a temporary data directory. The local management service listens on `127.0.0.1:8765`; Capture Bridge opens its separate LAN listener only during an active capture session.

Check the frontend without opening a window:

```sh
npm run typecheck
npm run build
```

## Run the local service by itself

For development only, run from the project root with Python 3.12.14 and the locked runtime dependencies installed:

```sh
python -m local_service
```

The default database is stored under the platform's local application-data directory. `--data-dir` and `MATH_GRADER_DATA_DIR` can select another local directory. `MATH_GRADER_RECOGNITION_CONFIG` can point to a JSON provider configuration; the versioned default is `local_service/config/recognition.json`.

## Application flow

The teacher workspace shows each Assignment's students, Submissions, and uploaded pages. Choose an existing workbook or analyze a new exam once; after the teacher confirms the answer key, later students in that Assignment reuse its temporary template. Recognition uses local providers, deterministic answer rules produce grading decisions, and uncertain items remain in the human review queue.

The Python service manages schema changes from `local_service/migrations/`, validates every Submission status transition in one state machine, and stores Recognition results and job failures in SQLite. Provider implementations are registered behind `RecognitionGateway`; adding a future provider does not require a Desktop or Submission-flow change.

Run the P0–P5 regression suite from a Python 3.12 development environment:

```sh
uv run --python 3.12.14 --extra dev --extra ocr --extra formula --extra vision python -m pytest
uv run --python 3.12.14 --extra dev --extra ocr --extra formula --extra vision python -m compileall -q benchmark local_service tests
```

## Retained P0-W1 Benchmark foundation

The P0-W1 model-neutral contracts, deterministic metrics, reference-only failure archive, and small CLI remain in `benchmark/`. They do not run OCR or VLM models. The built-in stub emits no answer and routes every question to review, so it exercises the benchmark pipeline without pretending to measure model accuracy. Model Benchmark is now scheduled for P6, after Recognition Integration.

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
