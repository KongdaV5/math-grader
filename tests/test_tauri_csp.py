import json
from pathlib import Path

import pytest

from scripts.tauri_csp import (
    LOOPBACK_IMAGE_ORIGIN,
    validate_tauri_csp,
    verify_policy_embedded,
)


ROOT = Path(__file__).resolve().parents[1]


def _production_policy():
    config = json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    return config["app"]["security"]["csp"]


def test_production_img_src_allows_only_loopback_image_service():
    policy = _production_policy()
    directives = validate_tauri_csp(policy)

    assert LOOPBACK_IMAGE_ORIGIN in directives["img-src"]
    assert "*" not in policy
    assert "http:" not in directives["img-src"]
    assert not any(source.startswith("http://192.168.") for source in directives["img-src"])


def test_built_executable_must_embed_the_validated_production_policy():
    policy = _production_policy()
    verify_policy_embedded(policy, b"Tauri compiled security policy: " + policy.encode("utf-8"))

    with pytest.raises(ValueError, match="does not contain"):
        verify_policy_embedded(policy, b"an older executable without the new img-src")


@pytest.mark.parametrize("policy", [
    "default-src *; img-src *",
    "default-src 'self'; img-src 'self' http:",
    "default-src 'self'; img-src 'self' asset: http://asset.localhost data: blob: http://127.0.0.1:8765 http://192.168.1.20:8766",
])
def test_rejects_broad_wildcard_scheme_or_lan_image_sources(policy):
    with pytest.raises(ValueError):
        validate_tauri_csp(policy)
