#!/usr/bin/env python3
"""Prepare a relocatable arm64 CPython runtime for the Tauri app bundle."""

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile


DEPENDENCIES = {
    "Pillow": "Pillow",
    "NumPy": "numpy",
    "OpenCV": "opencv-python-headless",
    "ONNX Runtime": "onnxruntime",
    "Hugging Face Hub": "huggingface-hub",
    "Paddle": "paddlepaddle",
    "PaddleOCR": "paddleocr",
    "MLX": "mlx",
    "mlx-vlm": "mlx-vlm",
}
IMPORT_SMOKE = ("PIL", "numpy", "cv2", "onnxruntime", "huggingface_hub",
                "paddle", "paddleocr", "mlx.core", "mlx_vlm")


def run(command, *, env=None, cwd=None):
    return subprocess.run(command, check=True, text=True, capture_output=True, env=env, cwd=cwd)


def safe_replace_directory(staging, output, allowed_parent):
    output = output.absolute()
    allowed_parent = allowed_parent.resolve()
    if not output.parent.resolve().is_relative_to(allowed_parent):
        raise RuntimeError("Runtime output must remain inside the ignored Tauri target directory")
    if output.is_symlink():
        raise RuntimeError("Refusing to replace a symlink at the runtime output path")
    if output.exists():
        if not output.is_dir():
            raise RuntimeError("Runtime output exists but is not a directory")
        shutil.rmtree(output)
    os.replace(staging, output)


def runtime_probe(python, site_packages):
    environment = {
        "HOME": str(Path(tempfile.gettempdir()) / "math-grader-runtime-home"),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(site_packages),
    }
    probe = """import importlib, platform, sys
versions = {{}}
for name in {imports!r}:
    module = importlib.import_module(name)
    if name == 'cv2':
        versions['opencv'] = module.__version__
print(sys.version.split()[0])
print(platform.machine())
print(sys.executable)
print(versions.get('opencv', 'unknown'))
""".format(imports=IMPORT_SMOKE)
    result = run([str(python), "-c", probe], env=environment, cwd=python.parent)
    lines = result.stdout.strip().splitlines()
    if len(lines) != 4 or lines[1] not in ("arm64", "aarch64"):
        raise RuntimeError("Bundled runtime import smoke returned unexpected identity: {}".format(lines))
    return {"python_version": lines[0], "architecture": "arm64", "executable": lines[2],
            "opencv_version": lines[3]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--runtime-version", default="0.1.0")
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--git-sha", required=True)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    target_root = (repo_root / "desktop/src-tauri/target").resolve()
    output = args.output.absolute()
    if platform.system() != "Darwin" or platform.machine() not in ("arm64", "aarch64"):
        raise SystemExit("The production runtime build is limited to Apple Silicon macOS")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Prepare this runtime with the pinned CPython 3.12 environment")
    if not output.parent.resolve().is_relative_to(target_root):
        raise SystemExit("Runtime output must be under desktop/src-tauri/target")

    base_python = Path(sys.base_prefix).resolve()
    site_packages = Path(sysconfig.get_paths()["purelib"]).resolve()
    source_executable = base_python / "bin/python3.12"
    if not source_executable.is_file() or not site_packages.is_dir():
        raise SystemExit("The pinned CPython runtime or site-packages directory is missing")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".math-grader-runtime-stage-", dir=output.parent))
    try:
        python_root = staging / "python"
        bundled_site = staging / "site-packages"
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
        shutil.copytree(base_python, python_root, symlinks=True, ignore=ignore)
        shutil.copytree(site_packages, bundled_site, symlinks=True, ignore=ignore)
        python = python_root / "bin/python3.12"
        smoke = runtime_probe(python, bundled_site)

        dependency_versions = {
            label: importlib.metadata.version(distribution)
            for label, distribution in DEPENDENCIES.items()
        }
        dependency_versions["OpenCV"] = smoke["opencv_version"]
        lock_path = repo_root / "uv.lock"
        manifest = {
            "manifest_schema_version": 1,
            "runtime_version": args.runtime_version,
            "app_version": args.app_version,
            "python_version": smoke["python_version"],
            "architecture": smoke["architecture"],
            "build_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_sha": args.git_sha,
            "bundle_format_version": 1,
            "packaging": "python-build-standalone + uv.lock site-packages",
            "dependency_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
            "dependencies": dependency_versions,
        }
        (staging / "runtime-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        # The bundled interpreter must be relocatable and resolve only bundled modules.
        verification = run([
            str(python), "-c",
            "import sys; print(sys.base_prefix); print('\\n'.join(sys.path))",
        ], env={
            "HOME": str(Path(tempfile.gettempdir()) / "math-grader-runtime-home"),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(bundled_site),
        }, cwd=python.parent).stdout.splitlines()
        development_paths = []
        for value in verification[1:]:
            if not value:
                continue
            resolved = Path(value).resolve()
            if resolved.is_relative_to(repo_root) and not resolved.is_relative_to(target_root):
                development_paths.append(value)
        if development_paths or str(site_packages) in "\n".join(verification):
            raise RuntimeError("Bundled Python still resolves a development path: {}".format(verification))
        safe_replace_directory(staging, output, target_root)
    except BaseException:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)
        raise

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print("Prepared runtime at {}".format(output))


if __name__ == "__main__":
    main()
