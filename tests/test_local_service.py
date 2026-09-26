import base64
import json
import time
from datetime import date
from http.server import ThreadingHTTPServer
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from local_service.database import Database
from local_service.http_server import create_server
from local_service.recognition import ProviderRegistry, RecognitionResult
from local_service.service import MathGraderService, ProcessingError, ValidationError
from local_service.state_machine import InvalidTransition, transition
from local_service.worker import JobWorker

PNG_IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def make_service(tmp_path, config=None, registry=None):
    config_path = None
    if config is not None:
        config_path = tmp_path / "recognition.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
    return MathGraderService(
        database_path=tmp_path / "data" / "math-grader.sqlite3",
        data_dir=tmp_path / "data",
        recognition_config=config_path,
        registry=registry,
    )


def make_records(service, student_no="001"):
    classroom = service.create_class("Class " + student_no)
    student = service.create_student(classroom["id"], student_no, "Student " + student_no)
    assignment = service.create_assignment(classroom["id"], "Worksheet", date.today().isoformat())
    return classroom, student, assignment


def make_submission(service, student_no="001", page_count=1):
    _, student, assignment = make_records(service, student_no)
    submission = service.create_submission(assignment["id"], student["id"])
    service.start_submission(submission["id"])
    for _ in range(page_count):
        service.add_placeholder_page(submission["id"])
    return service, submission


def test_sqlite_initializes_schema_and_class_student_assignment_path(tmp_path):
    service = make_service(tmp_path)

    with service.database.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"classes", "students", "assignments", "submissions", "submission_pages", "jobs"} <= tables

    classroom, student, assignment = make_records(service)
    assert service.list_classes() == [classroom]
    assert service.list_students(classroom["id"]) == [student]
    assert service.list_assignments(classroom["id"]) == [assignment]


def test_submission_supports_multiple_pages_and_tracks_count(tmp_path):
    service = make_service(tmp_path)
    _, student, assignment = make_records(service)
    submission = service.create_submission(assignment["id"], student["id"])

    service.start_submission(submission["id"])
    first = service.add_placeholder_page(submission["id"])
    second = service.add_page(submission["id"], "fixture://local-page-two")
    stored = service.get_submission(submission["id"])

    assert [first["page_index"], second["page_index"]] == [1, 2]
    assert stored["page_count"] == 2
    assert len(stored["pages"]) == 2
    assert stored["status"] == "CAPTURING"


def test_uploaded_test_image_is_stored_inside_local_data_directory(tmp_path):
    service = make_service(tmp_path)
    _, submission = make_submission(service, "image", page_count=0)

    page = service.add_uploaded_page(submission["id"], "worksheet.png", PNG_IMAGE)

    stored_path = service.data_dir / page["source_ref"]
    assert stored_path.read_bytes() == PNG_IMAGE
    assert page["page_index"] == 1
    assert page["mime_type"] == "image/png"
    assert page["byte_size"] == len(PNG_IMAGE)
    assert service.get_submission(submission["id"])["page_count"] == 1


def test_submission_state_machine_allows_valid_path_and_rejects_invalid_path(tmp_path):
    service = make_service(tmp_path)
    _, student, assignment = make_records(service)
    submission = service.create_submission(assignment["id"], student["id"])

    with service.database.connection() as connection:
        with pytest.raises(InvalidTransition, match="EMPTY to PROCESSING"):
            transition(connection, submission["id"], "PROCESSING", "2026-01-01T00:00:00+00:00")

    service.start_submission(submission["id"])
    service.add_placeholder_page(submission["id"])
    service.add_placeholder_page(submission["id"])
    queued = service.finish_submission(submission["id"])
    assert queued["status"] == "QUEUED"
    assert queued["page_count"] == 2
    assert queued["finished_capture_at"] is not None

    assert service.process_next_job() is True
    completed = service.get_submission(submission["id"])
    assert completed["status"] == "COMPLETED"
    assert completed["completed_at"] is not None
    assert completed["job"]["status"] == "COMPLETED"
    assert len(completed["results"]) == 2
    assert all(item["provider"] == "mock" for item in completed["results"])
    assert all(item["model"] == "mock-v1" for item in completed["results"])
    assert all(item["text"] == "23" for item in completed["results"])
    assert all(item["normalized_candidate"] == "23" for item in completed["results"])
    assert all(item["confidence"] == 0.99 for item in completed["results"])
    assert all(item["error"] is None for item in completed["results"])


def test_finish_requires_a_page_and_pages_cannot_be_added_after_finish(tmp_path):
    service = make_service(tmp_path)
    _, student, assignment = make_records(service)
    submission = service.create_submission(assignment["id"], student["id"])
    service.start_submission(submission["id"])

    with pytest.raises(ValidationError, match="at least one page"):
        service.finish_submission(submission["id"])

    service.add_placeholder_page(submission["id"])
    service.finish_submission(submission["id"])
    with pytest.raises(InvalidTransition, match="CAPTURING"):
        service.add_placeholder_page(submission["id"])


def test_student_must_belong_to_assignment_class(tmp_path):
    service = make_service(tmp_path)
    _, student, _ = make_records(service, "A")
    other_class = service.create_class("Other class")
    assignment = service.create_assignment(other_class["id"], "Worksheet", date.today().isoformat())

    with pytest.raises(ValidationError, match="same class"):
        service.create_submission(assignment["id"], student["id"])


def test_multiple_submissions_are_processed_in_queue_order(tmp_path):
    calls = []

    class RecordingProvider:
        def recognize(self, source_ref, answer_type, context=None):
            calls.append(source_ref)
            return RecognitionResult(
                text="result-{}".format(len(calls)), normalized_candidate="result-{}".format(len(calls)),
                confidence=1.0, provider="test", model="recording", metadata={"page": source_ref}
            )

    registry = ProviderRegistry()
    registry.register("recorder", lambda name, settings: RecordingProvider())
    config = {
        "recognition": {"default": {"primary": "recorder"}},
        "providers": {"recorder": {"type": "recorder", "model": "recording"}},
    }
    service = make_service(tmp_path, config=config, registry=registry)

    first_service, first = make_submission(service, "first")
    second_service, second = make_submission(service, "second")
    first_page = first_service.get_submission(first["id"])["pages"][0]["source_ref"]
    second_page = second_service.get_submission(second["id"])["pages"][0]["source_ref"]
    first_service.finish_submission(first["id"])
    second_service.finish_submission(second["id"])

    assert service.process_next_job() is True
    assert service.process_next_job() is True
    assert service.process_next_job() is False
    assert calls == [first_page, second_page]
    assert service.get_submission(first["id"])["status"] == "COMPLETED"
    assert service.get_submission(second["id"])["status"] == "COMPLETED"


def test_failed_job_is_recorded_and_worker_processes_following_job(tmp_path):
    calls = {"count": 0}

    class OnceFailingProvider:
        def recognize(self, source_ref, answer_type, context=None):
            calls["count"] += 1
            if calls["count"] == 1:
                return RecognitionResult(
                    provider="test", model="once-failing", latency_ms=1, error="test failure"
                )
            return RecognitionResult(
                text="ok", normalized_candidate="ok", confidence=1.0,
                provider="test", model="once-failing", latency_ms=1,
            )

    registry = ProviderRegistry()
    registry.register("once-failing", lambda name, settings: OnceFailingProvider())
    config = {
        "recognition": {"default": {"primary": "provider"}},
        "providers": {"provider": {"type": "once-failing", "model": "once-failing"}},
    }
    service = make_service(tmp_path, config=config, registry=registry)
    _, failed = make_submission(service, "fail")
    _, next_submission = make_submission(service, "next")
    service.finish_submission(failed["id"])
    service.finish_submission(next_submission["id"])

    assert service.process_next_job() is True
    failed_state = service.get_submission(failed["id"])
    assert failed_state["status"] == "FAILED"
    assert "test failure" in failed_state["error"]
    assert failed_state["job"]["status"] == "FAILED"
    assert "test failure" in failed_state["job"]["error"]
    assert failed_state["results"][0]["error"] == "test failure"

    assert service.process_next_job() is True
    assert service.get_submission(next_submission["id"])["status"] == "COMPLETED"
    assert calls["count"] == 2


def test_primary_provider_error_uses_configured_fallback(tmp_path):
    config = {
        "recognition": {"integer": {"primary": "primary", "fallback": "fallback"}},
        "providers": {
            "primary": {"type": "mock", "model": "primary-model", "error": "unavailable"},
            "fallback": {"type": "mock", "model": "fallback-model", "text": "configured"},
        },
    }
    service = make_service(tmp_path, config=config)

    result = service.gateway.recognize("fixture://page", "integer")

    assert result.provider == "mock"
    assert result.model == "fallback-model"
    assert result.text == "configured"
    assert result.metadata["fallback_from"] == "primary"
    assert result.metadata["fallback_error"] == "unavailable"


def test_provider_registry_supports_new_provider_types(tmp_path):
    class NewProvider:
        def recognize(self, source_ref, answer_type, context=None):
            return RecognitionResult(text="new-provider", provider="custom", model="local")

    registry = ProviderRegistry()
    registry.register("custom-type", lambda name, settings: NewProvider())
    config = {
        "recognition": {"default": {"primary": "local"}},
        "providers": {"local": {"type": "custom-type", "model": "local"}},
    }
    service = make_service(tmp_path, config=config, registry=registry)

    assert service.gateway.recognize("fixture://page", "short_text").text == "new-provider"


def test_http_and_background_worker_smoke(tmp_path):
    service = make_service(tmp_path)
    server = create_server(service, port=0)
    worker = JobWorker(service, poll_interval=0.01)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    worker.start()
    base = "http://127.0.0.1:{}".format(server.server_address[1])

    def request(method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request_obj = Request(
            base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request_obj, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    try:
        status, health = request("GET", "/health")
        assert status == 200 and health["status"] == "ok"
        _, classroom = request("POST", "/api/classes", {"name": "HTTP class"})
        _, student = request(
            "POST", "/api/classes/{}/students".format(classroom["id"]),
            {"student_no": "http-001", "name": "HTTP student"},
        )
        _, assignment = request(
            "POST", "/api/classes/{}/assignments".format(classroom["id"]),
            {"name": "HTTP assignment", "date": date.today().isoformat()},
        )
        _, submission = request(
            "POST", "/api/submissions",
            {"assignment_id": assignment["id"], "student_id": student["id"]},
        )
        request("POST", "/api/submissions/{}/start".format(submission["id"]), {})
        request("POST", "/api/submissions/{}/pages".format(submission["id"]), {"placeholder": True})
        status, queued = request("POST", "/api/submissions/{}/finish".format(submission["id"]), {})
        assert status == 202 and queued["status"] == "QUEUED"

        deadline = time.time() + 3
        current = queued
        while time.time() < deadline and current["status"] != "COMPLETED":
            time.sleep(0.02)
            _, current = request("GET", "/api/submissions/{}".format(submission["id"]))
        assert current["status"] == "COMPLETED"
        assert current["results"][0]["provider"] == "mock"
    finally:
        worker.stop()
        server.shutdown()
        server.server_close()
        serving.join(timeout=2)


def test_http_maps_invalid_state_transition_to_conflict(tmp_path):
    service = make_service(tmp_path)
    server = create_server(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:{}".format(server.server_address[1])
    try:
        classroom = service.create_class("State class")
        student = service.create_student(classroom["id"], "state-001", "State student")
        assignment = service.create_assignment(classroom["id"], "State work", date.today().isoformat())
        submission = service.create_submission(assignment["id"], student["id"])
        request = Request(
            base + "/api/submissions/{}/finish".format(submission["id"]),
            data=b"{}", method="POST", headers={"Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as response:
            urlopen(request, timeout=3)
        assert response.value.code == 409
        assert "CAPTURING" in response.value.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
