import json
from pathlib import Path
import sqlite3
import threading

import pytest

from local_service.database import Database
from local_service.errors import InvalidAnswerRegion, ModelNotInstalled, TemplateNotFound
from local_service.image_pipeline import ImagePipeline
from local_service.model_catalog import ModelCatalog
from local_service.model_manager import ModelManager
from local_service.model_providers import ModelProviderRegistry, RecognitionRequest
from local_service.recognition import RecognitionGateway
from local_service.runtime_paths import RuntimePaths
from local_service.templates import TemplateService


def fixture_catalog(tmp_path, **changes):
    model = {
        "id": "tiny-ocr", "display_name": "Tiny OCR", "category": "ocr", "description": "test",
        "provider_type": "ppocr_onnx", "runtime": "onnxruntime", "source": "fixture",
        "source_repo": ["test/tiny"], "upstream_repo": None, "requested_revision": "main",
        "artifact_kind": "onnx_bundle", "approximate_size_bytes": 2, "license": "Apache-2.0",
        "architecture": "test", "required": False, "recommended": "optional", "platform": ["macos-arm64"],
        "metadata": {}, "capabilities": ["ocr", "integer"],
        "artifacts": [{"name": "det", "repo": "test/tiny", "files": ["inference.onnx"]}],
    }
    model.update(changes)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"catalog_schema_version": 1, "models": [model]}))
    return path


class FakeDownloader:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def list_files(self, repo, revision, artifact):
        return "123456789abcdef", artifact["files"]

    def download_file(self, repo, revision, filename, directory):
        self.calls += 1
        if self.fail:
            raise OSError("fixture network failure")
        path = directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture-model")
        return path


def test_catalog_valid_and_invalid_schema(tmp_path):
    assert len(ModelCatalog().list()) == 5
    path = fixture_catalog(tmp_path)
    assert ModelCatalog(path).get("tiny-ocr")["runtime"] == "onnxruntime"
    path.write_text(json.dumps({"catalog_schema_version": 99, "models": []}))
    with pytest.raises(ValueError, match="schema"):
        ModelCatalog(path)


def test_catalog_rejects_duplicate_provider_and_traversal(tmp_path):
    path = fixture_catalog(tmp_path)
    data = json.loads(path.read_text())
    data["models"].append(data["models"][0])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="duplicate"):
        ModelCatalog(path)
    data["models"] = data["models"][:1]
    data["models"][0]["provider_type"] = "unknown"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="provider"):
        ModelCatalog(path)
    data["models"][0]["provider_type"] = "ppocr_onnx"
    data["models"][0]["artifacts"][0]["files"] = ["../escape"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="path"):
        ModelCatalog(path)


def manager_fixture(tmp_path, downloader=None, disk_usage=None):
    catalog = ModelCatalog(fixture_catalog(tmp_path))
    paths = RuntimePaths(tmp_path / "runtime")
    return ModelManager(catalog, paths, downloader=downloader or FakeDownloader(), disk_usage=disk_usage)


def test_model_manager_install_progress_verify_remove(tmp_path):
    downloader = FakeDownloader()
    manager = manager_fixture(tmp_path, downloader)
    assert manager.get_model_status("tiny-ocr")["state"] == "NOT_INSTALLED"
    assert manager.install_model("tiny-ocr", background=False)["state"] == "INSTALLED"
    manifest = manager.verify_model("tiny-ocr")
    assert manifest["resolved_revision"] == {"test/tiny": "123456789abcdef"}
    assert manifest["files"][0]["size"] == len(b"fixture-model")
    assert downloader.calls == 1
    assert manager.remove_model("tiny-ocr")["state"] == "NOT_INSTALLED"
    with pytest.raises(ModelNotInstalled):
        manager.verify_model("tiny-ocr")


def test_model_manager_failure_retry_and_atomicity(tmp_path):
    downloader = FakeDownloader(fail=True)
    manager = manager_fixture(tmp_path, downloader)
    state = manager.install_model("tiny-ocr", background=False)
    assert state["state"] == "ERROR"
    assert state["error"]["code"] == "MODEL_DOWNLOAD_FAILED"
    assert not (manager.paths.models / "tiny-ocr").exists()
    downloader.fail = False
    assert manager.retry_install("tiny-ocr", background=False)["state"] == "INSTALLED"
    assert not list((manager.paths.models / ".staging").iterdir())


def test_model_manager_disk_and_invalid_downloader_path(tmp_path):
    class LowDisk:
        free = 0
    manager = manager_fixture(tmp_path, disk_usage=lambda _: LowDisk())
    state = manager.install_model("tiny-ocr", background=False)
    assert state["error"]["code"] == "INSUFFICIENT_DISK_SPACE"

    class EscapingDownloader(FakeDownloader):
        def download_file(self, repo, revision, filename, directory):
            outside = tmp_path / "outside.onnx"
            outside.write_bytes(b"bad")
            return outside
    manager = manager_fixture(tmp_path, EscapingDownloader())
    state = manager.install_model("tiny-ocr", background=False)
    assert state["state"] == "ERROR"
    assert not (manager.paths.models / "tiny-ocr").exists()


def test_model_manager_real_file_progress_and_cancel(tmp_path):
    entered, release = threading.Event(), threading.Event()
    class PausingDownloader(FakeDownloader):
        def download_file(self, repo, revision, filename, directory):
            entered.set()
            assert release.wait(3)
            return super().download_file(repo, revision, filename, directory)
    manager = manager_fixture(tmp_path, PausingDownloader())
    manager.install_model("tiny-ocr")
    assert entered.wait(3)
    state = manager.get_model_status("tiny-ocr")
    assert state["state"] == "DOWNLOADING"
    assert state["progress"] == {"completed_files": 0, "total_files": 1, "current_file": "det/inference.onnx"}
    manager.cancel_install("tiny-ocr")
    release.set()
    for _ in range(100):
        if manager.get_model_status("tiny-ocr")["state"] == "ERROR":
            break
        threading.Event().wait(.01)
    assert manager.get_model_status("tiny-ocr")["state"] == "ERROR"
    assert not (manager.paths.models / "tiny-ocr").exists()


def test_provider_health_missing_and_load_error(tmp_path):
    manager = manager_fixture(tmp_path)
    registry = ModelProviderRegistry(manager.catalog, manager)
    assert registry.health("tiny-ocr")["state"] == "MODEL_NOT_INSTALLED"
    with pytest.raises(ModelNotInstalled):
        registry.get("tiny-ocr").execute(RecognitionRequest("/tmp/test.png", "integer", "integer"))
    manager.install_model("tiny-ocr", background=False)
    assert registry.health("tiny-ocr")["state"] == "LOADABLE"
    assert registry.health("tiny-ocr", load=True)["state"] == "MODEL_LOAD_FAILED"


def test_model_route_validation_and_missing_model_result(tmp_path):
    manager = manager_fixture(tmp_path)
    base = {"schema_version": 1, "recognition": {"default": {"primary": "mock"}},
            "providers": {"mock": {"type": "mock", "model": "test"}},
            "model_routes": {"integer": {"primary": "tiny-ocr"}}}
    gateway = RecognitionGateway(base, catalog=manager.catalog, manager=manager)
    result = gateway.recognize_request(RecognitionRequest("/tmp/image", "integer", "integer"))
    assert result.error == "MODEL_NOT_INSTALLED"
    base["model_routes"]["integer"]["primary"] = "unknown"
    with pytest.raises(KeyError):
        RecognitionGateway(base, catalog=manager.catalog, manager=manager)
    base["model_routes"] = {"formula": {"primary": "tiny-ocr"}}
    with pytest.raises(ValueError, match="does not support"):
        RecognitionGateway(base, catalog=manager.catalog, manager=manager)


def test_template_migration_crud_and_relationships(tmp_path):
    database = Database(tmp_path / "db.sqlite3")
    service = TemplateService(database)
    with database.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
    group = service.create_template_group("课本", "三年级", "上", "数学")
    assert service.list_template_groups()[0]["id"] == group["id"]
    page = service.create_page_template(group["id"], 1, "第一课")
    assert service.list_page_templates(group["id"])[0]["id"] == page["id"]
    question = service.create_question(page["id"], "1", "integer", "23", ["23"], 2)
    region = service.create_answer_region(question["id"], 1, .1, .2, .3, .4)
    assert region["coordinate_space"] == "normalized"
    assert service.get_page_template(page["id"])["questions"][0]["regions"][0]["id"] == region["id"]
    with pytest.raises(TemplateNotFound):
        service.create_page_template("missing", 2, "X")


def test_template_migration_preserves_p2_data(tmp_path):
    db_path = tmp_path / "existing.sqlite3"
    migrations = Path(__file__).resolve().parents[1] / "local_service" / "migrations"
    connection = sqlite3.connect(db_path)
    connection.executescript((migrations / "001_initial.sql").read_text())
    connection.executescript((migrations / "002_capture_bridge.sql").read_text())
    connection.execute("PRAGMA user_version = 2")
    connection.execute("INSERT INTO classes(id,name,active,created_at) VALUES('kept','Existing class',1,'2026-09-25')")
    connection.commit()
    connection.close()
    database = Database(db_path)
    with database.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert connection.execute("SELECT name FROM classes WHERE id='kept'").fetchone()[0] == "Existing class"


@pytest.mark.parametrize("bbox", [(-.1, 0, .3, .3), (.8, .1, .3, .3), (0, .9, .2, .2), (0, 0, 0, .1)])
def test_template_invalid_normalized_bbox(tmp_path, bbox):
    service = TemplateService(Database(tmp_path / "db.sqlite3"))
    group = service.create_template_group("课本", "三", "上", "数学")
    page = service.create_page_template(group["id"], 1, "第一页")
    question = service.create_question(page["id"], "1", "integer")
    with pytest.raises(InvalidAnswerRegion):
        service.create_answer_region(question["id"], 1, *bbox)


def synthetic(path, kind="normal"):
    import cv2
    import numpy as np
    image = np.full((500, 400, 3), 130, dtype=np.uint8)
    if kind != "no_page":
        cv2.rectangle(image, (42, 35), (360, 460), (250, 250, 250), -1)
        cv2.rectangle(image, (42, 35), (360, 460), (20, 20, 20), 5)
        cv2.putText(image, "23", (130, 250), cv2.FONT_HERSHEY_SIMPLEX, 2, (10, 10, 10), 4)
    if kind == "blur": image = cv2.GaussianBlur(image, (91, 91), 30)
    if kind == "dark": image[:] = 15
    if kind == "bright": image[:] = 250
    if kind == "rotated": image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if kind == "perspective":
        source = np.float32([[0,0],[399,0],[399,499],[0,499]])
        target = np.float32([[20,0],[380,30],[399,470],[0,499]])
        image = cv2.warpPerspective(image, cv2.getPerspectiveTransform(source,target), (400,500))
    cv2.imwrite(str(path), image)
    return path.read_bytes()


@pytest.mark.parametrize("kind", ["normal", "rotated", "perspective", "blur", "dark", "bright", "no_page"])
def test_image_pipeline_synthetic_and_source_preserved(tmp_path, kind):
    source = tmp_path / (kind + ".png")
    before = synthetic(source, kind)
    result = ImagePipeline(tmp_path / "processed").process(source)
    assert source.read_bytes() == before
    assert Path(result.processed_path).is_file()
    assert result.width > 0 and result.height > 0
    assert result.transform["exif_orientation"] == 1
    if kind == "no_page": assert result.status == "PAGE_NOT_FOUND"
    if kind == "dark": assert "UNDEREXPOSED" in result.warnings
    if kind == "bright": assert "OVEREXPOSED" in result.warnings
    if kind == "blur": assert "TOO_BLURRY" in result.warnings


def test_image_pipeline_applies_exif_orientation(tmp_path):
    from PIL import Image
    source = tmp_path / "oriented.jpg"
    image = Image.new("RGB", (80, 120), "white")
    exif = Image.Exif()
    exif[274] = 6
    image.save(source, exif=exif)
    before = source.read_bytes()
    result = ImagePipeline(tmp_path / "processed").process(source)
    assert source.read_bytes() == before
    assert result.transform["exif_orientation"] == 6
    assert (result.width, result.height) == (120, 80)
