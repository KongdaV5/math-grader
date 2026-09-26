# START HERE — Math Grader

## Current project state

- P0-W1 Benchmark Foundation: **PASS**.
- P1 Application Foundation, P3 Image Pipeline, P4 Template/Recognition, and P5-L1 Teacher Workflow: **PASS** for their defined synthetic-data integration gates.
- P5-L2 Production Runtime Packaging is the current work package. See `docs/project/STATUS.md`, `docs/project/TASK_BOARD.md`, and the latest handoff for its final result.
- P2 Capture Bridge remains **READY_FOR_DEVICE_TEST** until the complete real iPhone Safari acceptance flow is completed.
- Do not infer recognition accuracy from synthetic fixtures. Final Benchmark / Confidence is a separate future work package and does not start automatically.

## Use the app

Open **Math Grader.app** from Finder. The standalone app includes its own Python runtime; ordinary use does not require Python, Terminal, a virtual environment, or a separate model server. Install models from the in-app **模型中心**. App data and models live under `~/Library/Application Support/MathGrader/` and remain there when the app is replaced or deleted.

See [the user guide](docs/USER_GUIDE.md) for the teacher workflow and [the macOS build guide](docs/development/BUILD_MACOS.md) for developer packaging.

## Development

The product uses Tauri 2, React/TypeScript, a local Python service, SQLite, and bundled in-process providers. Use Python 3.12.14 and the committed `uv.lock` for development tests. From the repository root:

```sh
uv run --python 3.12.14 --extra dev --extra ocr --extra formula --extra vision python -m pytest
uv run --python 3.12.14 --extra dev --extra ocr --extra formula --extra vision python -m compileall -q benchmark local_service tests
```

From `desktop/`, run `npm ci`, `npm run typecheck`, `npm run build`, and `npm run desktop:dev` for frontend and development-client work. Build and install the standalone Apple Silicon app with `./scripts/build_macos_app.sh`.
