# START HERE — Math Grader

## Current project state

Start with [Project](</Users/kongda/Documents/Obsidian/obsidian-vault/Projects/Math-Grader/Project.md>) and [canonical Status](</Users/kongda/Documents/Obsidian/obsidian-vault/Projects/Math-Grader/Status.md>). Formal phase acceptance and remaining gates are recorded in [Releases](</Users/kongda/Documents/Obsidian/obsidian-vault/Projects/Math-Grader/Releases/Phase-Gates.md>). This repository keeps technical specifications, user/build instructions, schemas and benchmark tooling; it does not maintain a second current status or task board.

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
