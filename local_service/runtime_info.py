"""Runtime manifest and lightweight capability reporting for the packaged app."""

import importlib.metadata
import importlib
from importlib.util import find_spec
import json
import os
from pathlib import Path
import platform
import sys


MANIFEST_SCHEMA_VERSION = 1
DEPENDENCIES = {
    "Pillow": ("Pillow", "PIL"),
    "NumPy": ("numpy", "numpy"),
    "OpenCV": ("opencv-python-headless", "cv2"),
    "ONNX Runtime": ("onnxruntime", "onnxruntime"),
    "Hugging Face Hub": ("huggingface-hub", "huggingface_hub"),
    "Paddle": ("paddlepaddle", "paddle"),
    "PaddleOCR": ("paddleocr", "paddleocr"),
    "MLX": ("mlx", "mlx"),
    "mlx-vlm": ("mlx-vlm", "mlx_vlm"),
}
CAPABILITY_MODELS = {
    "ocr": ("pp-ocrv6-small", "pp-ocrv6-medium"),
    "formula": ("pp-formulanet-plus-m",),
    "vision": ("qwen3-vl-4b-mlx-4bit",),
}


class RuntimeManifestError(RuntimeError):
    pass


def runtime_manifest_path(executable=None, override=None):
    configured = override if override is not None else os.environ.get("MATH_GRADER_RUNTIME_MANIFEST")
    if configured:
        return Path(configured).expanduser().resolve()
    executable_path = Path(executable or sys.executable).resolve()
    # Bundled layout: Contents/Resources/runtime/python/bin/python3.12.
    if executable_path.parent.name == "bin" and executable_path.parent.parent.name == "python":
        return executable_path.parents[2] / "runtime-manifest.json"
    return None


def load_runtime_manifest(path=None):
    manifest_path = Path(path).expanduser().resolve() if path else runtime_manifest_path()
    if manifest_path is None or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeManifestError("Cannot read runtime manifest: {}".format(error)) from error
    required = ("manifest_schema_version", "runtime_version", "python_version", "architecture",
                "build_date", "bundle_format_version", "dependencies")
    if not isinstance(manifest, dict) or any(key not in manifest for key in required):
        raise RuntimeManifestError("Runtime manifest is missing required fields")
    if manifest["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise RuntimeManifestError("Unsupported runtime manifest schema")
    if not isinstance(manifest["dependencies"], dict):
        raise RuntimeManifestError("Runtime manifest dependencies must be an object")
    if manifest["architecture"] != platform.machine():
        raise RuntimeManifestError("Runtime architecture does not match this Mac")
    return manifest


def _module_available(module):
    try:
        return find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def dependency_versions():
    versions = {}
    for label, (distribution, module) in DEPENDENCIES.items():
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            version = None
        available = bool(version and _module_available(module))
        if label == "OpenCV" and available:
            try:
                version = importlib.import_module("cv2").__version__
            except (ImportError, OSError) as error:
                version = None
                available = False
        versions[label] = {"version": version, "available": available}
    return versions


def _capability_state(service, model_ids):
    installed = []
    installed_but_unavailable = False
    for model_id in model_ids:
        model = service.model_catalog.get(model_id)
        state = service.model_manager.get_model_status(model_id)["state"]
        if state != "INSTALLED":
            continue
        provider = service.gateway.model_registry.get(model_id)
        health = provider.health(load=False)
        if health["state"] in ("PROVIDER_UNAVAILABLE", "MODEL_LOAD_FAILED"):
            installed_but_unavailable = True
            continue
        if health["state"] == "READY":
            return {"state": "READY", "model_id": model_id, "runtime": model["runtime"]}
        installed.append((model_id, model["runtime"]))
    if installed:
        model_id, runtime = installed[0]
        return {"state": "AVAILABLE", "model_id": model_id, "runtime": runtime}
    if installed_but_unavailable:
        return {"state": "RUNTIME_UNAVAILABLE"}
    return None


def capability_health(service):
    modules = dependency_versions()
    image_ready = modules["Pillow"]["available"] and modules["OpenCV"]["available"]
    capabilities = {
        "image_processing": {"state": "AVAILABLE" if image_ready else "RUNTIME_UNAVAILABLE"},
    }
    runtime_dependencies = {"ocr": "ONNX Runtime", "formula": "PaddleOCR", "vision": "mlx-vlm"}
    for capability, model_ids in CAPABILITY_MODELS.items():
        status = _capability_state(service, model_ids)
        if status is not None:
            capabilities[capability] = status
        elif not modules[runtime_dependencies[capability]]["available"]:
            capabilities[capability] = {"state": "RUNTIME_UNAVAILABLE"}
        else:
            capabilities[capability] = {"state": "MODEL_NOT_INSTALLED"}
    return capabilities


def runtime_details(service=None):
    manifest = load_runtime_manifest()
    versions = dependency_versions()
    app_version = os.environ.get("MATH_GRADER_APP_VERSION", "development")
    git_sha = os.environ.get("MATH_GRADER_GIT_SHA", "unknown")
    if manifest:
        app_version = manifest.get("app_version", app_version)
        git_sha = manifest.get("git_sha", git_sha)
    return {
        "bundled": manifest is not None,
        "runtime_version": manifest.get("runtime_version") if manifest else "development",
        "python_version": platform.python_version(),
        "architecture": platform.machine(),
        "executable": str(Path(sys.executable).resolve()),
        "manifest_path": str(runtime_manifest_path()) if runtime_manifest_path() else None,
        "app_version": app_version,
        "git_sha": git_sha,
        "build_date": manifest.get("build_date") if manifest else None,
        "dependencies": versions,
        "capabilities": capability_health(service) if service else {},
    }
