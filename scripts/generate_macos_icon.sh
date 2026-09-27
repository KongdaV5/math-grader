#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ICON_DIR="$ROOT/desktop/src-tauri/icons"
PNG="$ICON_DIR/icon.png"
TEMP_DIR="$(mktemp -d /tmp/math-grader-icon.XXXXXX)"
ICONSET="$TEMP_DIR/icon.iconset"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS icon generation requires sips and iconutil." >&2
  exit 2
fi

cleanup() {
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

sips -s format png "$ICON_DIR/icon.svg" --out "$PNG" >/dev/null
mkdir -p "$ICONSET"

make_icon() {
  local pixels="$1"
  local filename="$2"
  sips -z "$pixels" "$pixels" "$PNG" --out "$ICONSET/$filename" >/dev/null
}

make_icon 16 icon_16x16.png
make_icon 32 icon_16x16@2x.png
make_icon 32 icon_32x32.png
make_icon 64 icon_32x32@2x.png
make_icon 128 icon_128x128.png
make_icon 256 icon_128x128@2x.png
make_icon 256 icon_256x256.png
make_icon 512 icon_256x256@2x.png
make_icon 512 icon_512x512.png
make_icon 1024 icon_512x512@2x.png

iconutil -c icns "$ICONSET" -o "$ICON_DIR/icon.icns"
