import json
import platform
from pathlib import Path

import pytest

from local_service.model_catalog import ModelCatalog
from local_service.model_manager import ModelManager
from local_service.runtime_info import (
    RuntimeManifestError,
    capability_health,
    load_runtime_manifest,
    runtime_manifest_path,
)
from local_service.runtime_paths import RuntimePaths, default_root
from local_service.service import MathGraderService


def write_manifest(path, **overrides):
    manifest = {
        "manifest_schema_version": 1,
        "runtime_version": "0.1.0",
        "python_version": "3.12.14",
        "architecture": platform.machine(),
        "build_date": "2026-09-26T00:00:00+00:00",
        "bundle_format_version": 1,
        "dependencies": {"Pillow": "11.3.0"},
        **overrides,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def tiny_catalog(tmp_path):
    model = {
        "id": "tiny-ocr", "display_name": "Tiny OCR", "category": "ocr", "description": "test",
        "provider_type": "ppocr_onnx", "runtime": "onnxruntime", "source": "fixture",
        "source_repo": ["test/tiny"], "upstream_repo": None, "requested_revision": "main",
        "artifact_kind": "onnx_bundle", "approximate_size_bytes": 2, "license": "Apache-2.0",
        "architecture": "test", "required": False, "recommended": "optional", "platform": ["macos-arm64"],
        "metadata": {}, "capabilities": ["ocr", "integer"],
        "artifacts": [{"name": "det", "repo": "test/tiny", "files": ["inference.onnx"]}],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"catalog_schema_version": 1, "models": [model]}), encoding="utf-8")
    return ModelCatalog(path)


def test_runtime_manifest_load_and_infer_bundle_path(tmp_path):
    executable = tmp_path / "Math Grader.app/Contents/Resources/runtime/python/bin/python3.12"
    manifest_path = executable.parents[2] / "runtime-manifest.json"
    expected = write_manifest(manifest_path)

    assert runtime_manifest_path(executable=executable) == manifest_path
    assert load_runtime_manifest(manifest_path) == expected


def test_runtime_manifest_rejects_unsupported_schema_and_wrong_architecture(tmp_path):
    path = tmp_path / "runtime-manifest.json"
    write_manifest(path, manifest_schema_version=99)
    with pytest.raises(RuntimeManifestError, match="schema"):
        load_runtime_manifest(path)
    write_manifest(path, architecture="not-this-machine")
    with pytest.raises(RuntimeManifestError, match="architecture"):
        load_runtime_manifest(path)


def test_application_support_root_and_managed_model_path_are_separate(tmp_path, monkeypatch):
    home = tmp_path / "profile-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("MATH_GRADER_DATA_DIR", raising=False)
    monkeypatch.delenv("MATH_GRADER_MODELS_DIR", raising=False)
    assert default_root() == home / "Library/Application Support/MathGrader"

    support = default_root()
    paths = RuntimePaths(support)
    assert paths.models == support / "models"
    external_models = tmp_path / "copied-models"
    monkeypatch.setenv("MATH_GRADER_MODELS_DIR", str(external_models))
    assert RuntimePaths(support).models == external_models
    monkeypatch.setenv("MATH_GRADER_MODELS_DIR", "relative-models")
    with pytest.raises(ValueError, match="absolute path"):
        RuntimePaths(support)


def test_model_install_manifest_path_is_portable_between_application_support_roots(tmp_path):
    catalog = tiny_catalog(tmp_path)
    first = RuntimePaths(tmp_path / "mac-a" / "Library/Application Support/MathGrader").ensure()
    second = RuntimePaths(tmp_path / "mac-b" / "Library/Application Support/MathGrader").ensure()
    model = catalog.get("tiny-ocr")
    old_install = first.models / model["id"]
    new_install = second.models / model["id"]
    model_file = old_install / "det/inference.onnx"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_bytes(b"ok")
    files = [{"path": "det/inference.onnx", "size": 2}]
    (old_install / "install-manifest.json").write_text(json.dumps({
        "model_id": model["id"],
        "catalog_schema_version": catalog.schema_version,
        "source_repo": model["source_repo"],
        "requested_revision": model["requested_revision"],
        "resolved_revision": {repo: "123456789abcdef" for repo in model["source_repo"]},
        "installed_at": "2026-09-26T00:00:00+00:00",
        "local_path": str(old_install),
        "files": files,
        "expected_size": model["approximate_size_bytes"],
        "actual_size": 2,
        "state": "INSTALLED",
        "runtime": model["runtime"],
        "provider_type": model["provider_type"],
    }), encoding="utf-8")

    manager = ModelManager(catalog, second)
    # Moving the model directory is sufficient. The old absolute path in a P4
    # manifest is informational and is never used to locate the model files.
    import shutil
    shutil.copytree(old_install, new_install)
    assert manager.verify_model(model["id"])["local_path"] == str(old_install)
    assert manager.get_model_status(model["id"])["path"] == str(new_install)


def test_new_model_installs_use_relative_manifest_path(tmp_path):
    class Downloader:
        def list_files(self, repo, revision, artifact):
            return "123456789abcdef", sorted(set(artifact["files"]))

        def download_file(self, repo, revision, filename, directory):
            path = Path(directory) / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic-model-file")
            return path

    catalog = tiny_catalog(tmp_path)
    manager = ModelManager(catalog, RuntimePaths(tmp_path / "runtime"), downloader=Downloader(),
                          disk_usage=lambda _: type("Disk", (), {"free": 10**9})())
    assert manager.install_model("tiny-ocr", background=False)["state"] == "INSTALLED"
    assert manager.verify_model("tiny-ocr")["local_path"] == "models/tiny-ocr"


def test_capability_health_separates_uninstalled_models_and_runtime(tmp_path):
    service = MathGraderService(tmp_path / "profile/data.sqlite3", data_dir=tmp_path / "profile")
    capabilities = capability_health(service)
    assert capabilities["image_processing"]["state"] in ("AVAILABLE", "RUNTIME_UNAVAILABLE")
    assert capabilities["ocr"]["state"] == "MODEL_NOT_INSTALLED"
    assert capabilities["formula"]["state"] == "MODEL_NOT_INSTALLED"
    assert capabilities["vision"]["state"] == "MODEL_NOT_INSTALLED"
    assert service.gateway.model_registry.providers == {}
