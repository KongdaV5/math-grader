# Build the standalone macOS app

This guide is for developers packaging Math Grader. It does not describe the ordinary teacher workflow.

## Target and prerequisites

- Apple Silicon (`arm64`) Mac running macOS 15.0 or newer.
- Xcode Command Line Tools, Rust/Cargo, Node.js/npm, and `uv` available to the developer.
- The repository's pinned CPython 3.12.14 managed by `uv`; the script downloads it into the developer runtime cache when needed.
- Internet access while preparing a first build. Python wheels and Node/Rust build dependencies are cached for later builds.

The current locked MLX wheel is tagged for macOS 15.0+ arm64. The app deliberately records this minimum in `tauri.conf.json`. Intel Macs and macOS 14 or older are outside this build target.

## One-command build

From the repository root, run:

```sh
./scripts/build_macos_app.sh
```

The command checks `uv.lock`, prepares the bundled runtime, builds the frontend and Tauri app for `aarch64-apple-darwin`, signs the local app bundle ad hoc, verifies the bundle and native architectures, and installs the result at `~/Desktop/Math Grader.app`.

Build artifacts and the dependency environment are under `desktop/src-tauri/target/`, which is ignored by Git. `uv` keeps its downloaded Python distribution and wheel cache outside the repository. `uv.lock` pins the resolved Python dependency set; `desktop/package-lock.json` and `desktop/src-tauri/Cargo.lock` pin the frontend and Rust dependencies.

## Runtime architecture

The app contains a relocatable python-build-standalone CPython 3.12.14 distribution and the locked runtime packages under `Contents/Resources/runtime/`. The Python service sources and their migrations/configuration are under `Contents/Resources/local_service/`. Release Rust code selects the explicit in-bundle executable and manifest; it has no system-Python fallback. The service is launched with a clean Python environment and a working directory under Application Support.

The runtime manifest is versioned independently from the app version and records Python, architecture, dependency versions, build date, lockfile hash, and source Git SHA. The Settings page and `/health` expose the actual runtime identity and capability states. No model weights are included in the app.

Installed models remain in:

```text
~/Library/Application Support/MathGrader/models/<model-id>/
```

The service's SQLite database, uploaded photographs, processed pages, crops, cache, logs, and configuration also remain under `~/Library/Application Support/MathGrader/`. Deleting or replacing the `.app` does not delete this directory. New model manifests store `models/<model-id>`; older absolute manifest paths are accepted only as legacy metadata while ModelManager resolves files from the configured managed model root. Submission image paths are relative to the data root.

The normal app starts no model weights. A provider loads its model only when an inference request runs; the Model Center can report `MODEL_NOT_INSTALLED`, `RUNTIME_UNAVAILABLE`, `AVAILABLE`, or `READY` separately.

## Local signing and release signing

The build script applies a local ad-hoc signature and runs `codesign --verify --deep --strict`. It does not notarize the app. The current package configuration leaves hardened runtime disabled; before Developer ID distribution, retest MLX, Paddle, and ONNX under the chosen hardened runtime and entitlements, then sign and notarize with the release identity. Downloaded/quarantined distribution and Gatekeeper acceptance are not certified by this local build.

## Useful checks

The build script verifies that the final app contains the P5 frontend, service code, Python interpreter, locked native libraries for arm64, and runtime manifest, and that it contains no `.safetensors` model weights. It separately verifies the app signature. To inspect a local build:

```sh
codesign --verify --deep --strict --verbose=2 "$HOME/Desktop/Math Grader.app"
du -sh "$HOME/Desktop/Math Grader.app"
```

Real bundled model inference is exercised by `scripts/smoke_bundled_models.py` after installing an app. Run it through the app-bundled Python with `PYTHONPATH` set to the app's `Contents/Resources` and `Contents/Resources/runtime/site-packages`, `MATH_GRADER_MODELS_DIR` pointed to the managed model directory, and a synthetic-only temporary data directory. Do not point the smoke at student records.
