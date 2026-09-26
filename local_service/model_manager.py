"""Explicit model installs with staging, manifest verification and no startup download."""

from datetime import datetime, timezone
from fnmatch import fnmatch
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Event, RLock, Thread
import uuid

from local_service.errors import (InsufficientDiskSpace, ModelDownloadFailed,
                                  ModelNotInstalled, ModelVerifyFailed)
from local_service.model_catalog import safe_relative_path


class HuggingFaceDownloader:
    def list_files(self, repo, revision, artifact):
        from huggingface_hub import HfApi
        info = HfApi().model_info(repo, revision=revision, files_metadata=True)
        patterns = artifact.get("patterns")
        files = []
        for sibling in info.siblings:
            name = sibling.rfilename
            safe_relative_path(name)
            if name in artifact["files"] or (patterns and any(fnmatch(name, p) for p in patterns)):
                files.append(name)
        if not set(artifact["files"]) <= set(files):
            raise ModelDownloadFailed("Source repository is missing required files")
        if patterns and not any(name.endswith(".safetensors") for name in files):
            raise ModelDownloadFailed("Source repository has no model weights")
        return info.sha, sorted(files)

    def download_file(self, repo, revision, filename, directory):
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(repo_id=repo, revision=revision, filename=filename,
                                    local_dir=str(directory)))


class ModelManager:
    def __init__(self, catalog, paths, downloader=None, disk_usage=None):
        self.catalog = catalog
        self.paths = paths
        self.paths.ensure()
        self.downloader = downloader or HuggingFaceDownloader()
        self.disk_usage = disk_usage or shutil.disk_usage
        self._lock = RLock()
        self._jobs = {}

    def _directory(self, model_id):
        self.catalog.get(model_id)
        return self.paths.models / model_id

    def get_model_status(self, model_id):
        model = self.catalog.get(model_id)
        with self._lock:
            job = self._jobs.get(model_id)
            if job and job["state"] in ("QUEUED", "DOWNLOADING", "VERIFYING", "ERROR", "REMOVING"):
                return {"model": model, **{k: v for k, v in job.items() if k != "cancel_event"}}
        directory = self._directory(model_id)
        if directory.is_dir() and not directory.is_symlink() and (directory / "install-manifest.json").is_file():
            return {"model": model, "state": "INSTALLED", "path": str(directory), "progress": None, "error": None}
        if directory.exists() or directory.is_symlink():
            return {"model": model, "state": "ERROR", "path": str(directory), "progress": None,
                    "error": {"code": "MODEL_VERIFY_FAILED", "message": "Model directory has no valid install manifest"}}
        return {"model": model, "state": "NOT_INSTALLED", "path": None, "progress": None, "error": None}

    def list_models(self):
        return [self.get_model_status(model["id"]) for model in self.catalog.list()]

    def _set(self, model_id, **values):
        with self._lock:
            self._jobs[model_id].update(values)

    def install_model(self, model_id, background=True):
        self.catalog.get(model_id)
        with self._lock:
            current = self.get_model_status(model_id)["state"]
            if current == "INSTALLED":
                return self.get_model_status(model_id)
            if current in ("QUEUED", "DOWNLOADING", "VERIFYING", "REMOVING"):
                raise ValueError("Model operation already in progress")
            self._jobs[model_id] = {"state": "QUEUED", "path": None,
                                    "progress": {"completed_files": 0, "total_files": None, "current_file": None},
                                    "error": None, "cancel_event": Event()}
        if background:
            Thread(target=self._install, args=(model_id,), daemon=True, name="model-" + model_id).start()
        else:
            self._install(model_id)
        return self.get_model_status(model_id)

    def _install(self, model_id):
        model = self.catalog.get(model_id)
        stage = self.paths.models / ".staging" / (model_id + "-" + uuid.uuid4().hex)
        destination = self._directory(model_id)
        try:
            estimate = model["approximate_size_bytes"]
            # Download and the local-dir staging copy can coexist during transfer.
            required = int(estimate * 1.35) + 100 * 1024 * 1024
            if self.disk_usage(self.paths.models).free < required:
                raise InsufficientDiskSpace("Need at least {:.1f} GB free to install {}".format(required / 1e9, model_id))
            stage.mkdir(parents=True, exist_ok=False)
            self._set(model_id, state="DOWNLOADING")
            plans = []
            for artifact in model["artifacts"]:
                sha, files = self.downloader.list_files(artifact["repo"], model["requested_revision"], artifact)
                if not isinstance(sha, str) or len(sha) < 7:
                    raise ModelDownloadFailed("Source did not resolve a commit revision")
                plans.append((artifact, sha, files))
            total = sum(len(files) for _, _, files in plans)
            self._set(model_id, progress={"completed_files": 0, "total_files": total, "current_file": None})
            records = []
            revisions = {}
            completed = 0
            for artifact, sha, files in plans:
                revisions[artifact["repo"]] = sha
                part_dir = stage / artifact["name"]
                part_dir.mkdir()
                for filename in files:
                    if self._jobs[model_id]["cancel_event"].is_set():
                        raise ModelDownloadFailed("Installation cancelled")
                    safe_relative_path(filename)
                    self._set(model_id, progress={"completed_files": completed, "total_files": total,
                                                  "current_file": artifact["name"] + "/" + filename})
                    path = Path(self.downloader.download_file(artifact["repo"], sha, filename, part_dir))
                    expected = (part_dir / filename).resolve()
                    if path.resolve() != expected or not expected.is_relative_to(part_dir.resolve()):
                        raise ModelDownloadFailed("Downloader returned a path outside staging")
                    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
                        raise ModelDownloadFailed("Downloaded artifact is empty or invalid")
                    records.append({"path": artifact["name"] + "/" + filename, "size": path.stat().st_size})
                    completed += 1
                    self._set(model_id, progress={"completed_files": completed, "total_files": total,
                                                  "current_file": None})
            if self._jobs[model_id]["cancel_event"].is_set():
                raise ModelDownloadFailed("Installation cancelled")
            self._set(model_id, state="VERIFYING")
            manifest = {
                "model_id": model_id, "catalog_schema_version": self.catalog.schema_version,
                "source_repo": model["source_repo"], "requested_revision": model["requested_revision"],
                "resolved_revision": revisions, "installed_at": datetime.now(timezone.utc).isoformat(),
                "local_path": str(destination), "files": records, "expected_size": estimate,
                "actual_size": sum(item["size"] for item in records), "state": "INSTALLED",
                "runtime": model["runtime"], "provider_type": model["provider_type"],
            }
            (stage / "install-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            self._verify_directory(stage, model, manifest)
            if destination.exists() or destination.is_symlink():
                raise ModelVerifyFailed("Model directory already exists")
            os.replace(stage, destination)
            with self._lock:
                self._jobs.pop(model_id, None)
        except Exception as error:
            code = error.code if hasattr(error, "code") else "MODEL_DOWNLOAD_FAILED"
            self._set(model_id, state="ERROR", error={"code": code, "message": str(error)}, path=None)
        finally:
            if stage.exists() and not stage.is_symlink():
                shutil.rmtree(stage)

    def _verify_directory(self, directory, model, manifest=None):
        manifest_path = directory / "install-manifest.json"
        try:
            data = manifest or json.loads(manifest_path.read_text(encoding="utf-8"))
            if data["model_id"] != model["id"] or data["catalog_schema_version"] != self.catalog.schema_version:
                raise ValueError("Manifest model or schema mismatch")
            if data["source_repo"] != model["source_repo"] or data["provider_type"] != model["provider_type"]:
                raise ValueError("Manifest source or provider mismatch")
            if (data["requested_revision"] != model["requested_revision"] or
                data["runtime"] != model["runtime"] or data["state"] != "INSTALLED" or
                data["local_path"] != str(self._directory(model["id"])) or
                data["expected_size"] != model["approximate_size_bytes"] or
                not data["installed_at"]):
                raise ValueError("Manifest install metadata mismatch")
            if set(data["resolved_revision"]) != set(model["source_repo"]):
                raise ValueError("Missing resolved revision")
            files = {record["path"]: record for record in data["files"]}
            for artifact in model["artifacts"]:
                for filename in artifact["files"]:
                    if artifact["name"] + "/" + filename not in files:
                        raise ValueError("Missing required artifact")
                if artifact.get("patterns") and not any(
                    name.startswith(artifact["name"] + "/") and name.endswith(".safetensors") for name in files
                ):
                    raise ValueError("Missing model weights")
            for relative, record in files.items():
                safe_relative_path(relative)
                path = directory / relative
                if (path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or
                    not path.is_file() or path.stat().st_size != record["size"] or record["size"] <= 0):
                    raise ValueError("Artifact missing or size changed: " + relative)
            if data["actual_size"] != sum(record["size"] for record in files.values()):
                raise ValueError("Manifest size mismatch")
        except (KeyError, ValueError, OSError, TypeError) as error:
            raise ModelVerifyFailed(str(error)) from error
        return data

    def verify_model(self, model_id):
        model = self.catalog.get(model_id)
        directory = self._directory(model_id)
        if not directory.is_dir() or directory.is_symlink():
            raise ModelNotInstalled(model_id)
        return self._verify_directory(directory, model)

    def cancel_install(self, model_id):
        self.catalog.get(model_id)
        with self._lock:
            job = self._jobs.get(model_id)
            if not job or job["state"] not in ("QUEUED", "DOWNLOADING", "VERIFYING"):
                raise ValueError("No active install to cancel")
            job["cancel_event"].set()
        return self.get_model_status(model_id)

    def retry_install(self, model_id, background=True):
        if self.get_model_status(model_id)["state"] != "ERROR":
            raise ValueError("Only a failed install can be retried")
        return self.install_model(model_id, background=background)

    def remove_model(self, model_id, can_remove=None):
        directory = self._directory(model_id)
        with self._lock:
            state = self.get_model_status(model_id)["state"]
            if state in ("QUEUED", "DOWNLOADING", "VERIFYING", "REMOVING"):
                raise ValueError("Model is busy")
            if can_remove and not can_remove(model_id):
                raise ValueError("Model is currently loaded or in use")
            if not directory.is_dir() or directory.is_symlink():
                raise ModelNotInstalled(model_id)
            self._jobs[model_id] = {"state": "REMOVING", "path": str(directory), "progress": None,
                                    "error": None, "cancel_event": Event()}
            shutil.rmtree(directory)
            self._jobs.pop(model_id, None)
        return self.get_model_status(model_id)

    def open_model_directory(self, model_id):
        directory = self._directory(model_id)
        if not directory.is_dir() or directory.is_symlink():
            raise ModelNotInstalled(model_id)
        if sys.platform != "darwin":
            return str(directory)
        subprocess.Popen(["open", str(directory)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(directory)
