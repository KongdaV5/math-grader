"""Versioned, validated allowlist of installable model artifacts."""

import json
from pathlib import Path, PurePosixPath
import re


PROVIDER_CAPABILITIES = {
    "ppocr_onnx": {"ocr", "integer", "decimal", "short_text", "choice", "boolean", "comparison_symbol", "sequence", "multi_blank"},
    "paddle_formula": {"formula", "fraction"},
    "mlx_vlm": {"vision", "integer", "decimal", "short_text", "formula", "fraction", "choice", "boolean", "comparison_symbol", "sequence", "multi_blank"},
}
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REPO_ID = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def safe_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Invalid artifact path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in (".", "..") for part in value.split("/")):
        raise ValueError("Invalid artifact path")
    return path


class ModelCatalog:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).parent / "config/model_catalog.json"
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if raw.get("catalog_schema_version") != 1 or not isinstance(raw.get("models"), list):
            raise ValueError("Unsupported model catalog schema")
        self.schema_version = 1
        self.models = {}
        required = {"id", "display_name", "category", "description", "provider_type", "runtime",
                    "source", "source_repo", "requested_revision", "artifact_kind", "approximate_size_bytes",
                    "license", "architecture", "required", "recommended", "platform", "metadata", "artifacts", "capabilities"}
        for model in raw["models"]:
            if not isinstance(model, dict) or not required <= model.keys():
                raise ValueError("Incomplete model catalog entry")
            model_id = model["id"]
            if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id) or model_id in self.models:
                raise ValueError("Invalid or duplicate model ID")
            provider_type = model["provider_type"]
            if provider_type not in PROVIDER_CAPABILITIES:
                raise ValueError("Unknown provider type")
            if not isinstance(model["capabilities"], list) or not set(model["capabilities"]) <= PROVIDER_CAPABILITIES[provider_type]:
                raise ValueError("Invalid model capability")
            if not isinstance(model["approximate_size_bytes"], int) or model["approximate_size_bytes"] <= 0:
                raise ValueError("Invalid model size")
            if not isinstance(model["artifacts"], list) or not model["artifacts"]:
                raise ValueError("Model has no artifacts")
            names = set()
            for artifact in model["artifacts"]:
                name, repo = artifact.get("name"), artifact.get("repo")
                if not isinstance(name, str) or not MODEL_ID.fullmatch(name) or name in names:
                    raise ValueError("Invalid artifact name")
                names.add(name)
                if not isinstance(repo, str) or not REPO_ID.fullmatch(repo) or repo not in model["source_repo"]:
                    raise ValueError("Invalid artifact repo")
                for filename in artifact.get("files", []):
                    safe_relative_path(filename)
                for pattern in artifact.get("patterns", []):
                    safe_relative_path(pattern)
            self.models[model_id] = model

    def get(self, model_id):
        try:
            return self.models[model_id]
        except (KeyError, TypeError):
            raise KeyError("Unknown catalog model: {}".format(model_id))

    def list(self):
        return list(self.models.values())
