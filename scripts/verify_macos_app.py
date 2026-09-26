#!/usr/bin/env python3
"""Inspect the built app bundle instead of trusting the Tauri build exit code."""

import argparse
import json
from pathlib import Path
import plistlib
import subprocess


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def verify_arch(path):
    subprocess.run(["/usr/bin/lipo", str(path), "-verify_arch", "arm64"], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("--git-sha", required=True)
    args = parser.parse_args()
    app = args.app.resolve()
    resources = app / "Contents/Resources"
    runtime = resources / "runtime"
    executable = app / "Contents/MacOS/math-grader-desktop"
    manifest_path = runtime / "runtime-manifest.json"
    require(app.is_dir(), "Math Grader.app bundle is missing")
    require(executable.is_file(), "Tauri desktop executable is missing")
    require((resources / "local_service/capture_page.html").is_file(), "P2 Capture page is missing")
    require((resources / "local_service/runtime_info.py").is_file(), "P5-L2 runtime health code is missing")
    require((runtime / "python/bin/python3.12").is_file(), "Bundled Python executable is missing")
    require((runtime / "site-packages/onnxruntime/__init__.py").is_file(), "Bundled ONNX Runtime is missing")
    require((runtime / "site-packages/paddleocr/__init__.py").is_file(), "Bundled PaddleOCR is missing")
    require((runtime / "site-packages/mlx_vlm/__init__.py").is_file(), "Bundled mlx-vlm is missing")
    require(manifest_path.is_file(), "Bundled runtime manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("git_sha") == args.git_sha, "Runtime manifest Git SHA does not match this build")
    require(manifest.get("architecture") == "arm64", "Runtime manifest is not Apple Silicon arm64")
    require(manifest.get("python_version", "").startswith("3.12."), "Bundled Python version is not pinned CPython 3.12")
    require(manifest.get("dependencies"), "Runtime dependency versions were not recorded")
    plist = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    require(plist.get("CFBundleIdentifier") == "local.math-grader.desktop", "Unexpected app bundle identifier")
    require(plist.get("CFBundleShortVersionString") == manifest.get("app_version"), "App version does not match runtime manifest")
    verify_arch(executable)
    verify_arch(runtime / "python/bin/python3.12")
    for candidate in (
        runtime / "site-packages/mlx/core.cpython-312-darwin.so",
        runtime / "site-packages/mlx/lib/libmlx.dylib",
        runtime / "site-packages/paddle/base/libpaddle.so",
        runtime / "site-packages/onnxruntime/capi/onnxruntime_pybind11_state.so",
    ):
        require(candidate.is_file(), "Bundled native dependency is missing: {}".format(candidate))
        verify_arch(candidate)
    weights = list(runtime.rglob("*.safetensors"))
    require(not weights, "Model weights must remain in Application Support, not the app bundle")
    javascript = "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                            for path in (resources / "assets").glob("*.js"))
    require("人工复核" in javascript and "自动分析本次试卷" in javascript,
            "Built frontend does not contain the P5 teacher workflow UI")
    print(json.dumps({
        "app": str(app),
        "bundle_id": plist["CFBundleIdentifier"],
        "app_version": plist["CFBundleShortVersionString"],
        "runtime_version": manifest["runtime_version"],
        "python_version": manifest["python_version"],
        "architecture": manifest["architecture"],
        "git_sha": manifest["git_sha"],
        "dependencies": manifest["dependencies"],
        "model_weights_in_bundle": len(weights),
        "p5_ui": "present",
        "capture_page": "present",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
