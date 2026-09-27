#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP="$ROOT/desktop"
TAURI="$DESKTOP/src-tauri"
BUILD_ENV="$TAURI/target/math-grader-runtime-build-env"
RUNTIME_OUT="$TAURI/target/math-grader-runtime"
APP="$TAURI/target/aarch64-apple-darwin/release/bundle/macos/Math Grader.app"
GIT_SHA="$(git -C "$ROOT" rev-parse HEAD)"
APP_VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$TAURI/Cargo.toml" | head -1)"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "P5-L2 production packaging requires Apple Silicon macOS." >&2
  exit 2
fi
if [[ -z "$APP_VERSION" ]]; then
  echo "Cannot read the Math Grader app version from Cargo.toml." >&2
  exit 2
fi

cd "$ROOT"
uv lock --check
UV_PROJECT_ENVIRONMENT="$BUILD_ENV" uv sync --locked --no-dev --no-install-project \
  --extra ocr --extra formula --extra vision --python 3.12.14 --python-preference only-managed
"$BUILD_ENV/bin/python" "$ROOT/scripts/prepare_macos_runtime.py" \
  --repo-root "$ROOT" --output "$RUNTIME_OUT" --app-version "$APP_VERSION" --git-sha "$GIT_SHA"

cd "$DESKTOP"
npm ci
"$ROOT/scripts/generate_macos_icon.sh"
MACOSX_DEPLOYMENT_TARGET=15.0 npm run desktop:build -- --target aarch64-apple-darwin

if [[ ! -d "$APP" ]]; then
  echo "Tauri build did not produce the expected Apple Silicon app: $APP" >&2
  exit 1
fi
codesign --force --deep --sign - --timestamp=none "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
"$BUILD_ENV/bin/python" "$ROOT/scripts/verify_macos_app.py" "$APP" \
  --git-sha "$GIT_SHA" --frontend-dist "$DESKTOP/dist"
"$BUILD_ENV/bin/python" "$ROOT/scripts/install_macos_app.py" "$APP"
codesign --verify --deep --strict "$HOME/Desktop/Math Grader.app"
du -sh "$HOME/Desktop/Math Grader.app"
