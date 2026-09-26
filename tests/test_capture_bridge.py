import base64
from datetime import date
import hashlib
import json
import threading
import time
import uuid
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest

from local_service.capture_bridge import CaptureBridge, discover_lan_ipv4_addresses
from local_service.http_server import create_server
from local_service.recognition import ProviderRegistry, RecognitionResult
from local_service.service import (
    MathGraderService,
    NotFound,
    PayloadTooLarge,
    Unauthorized,
    UnsupportedMediaType,
    ValidationError,
)
from local_service.state_machine import InvalidTransition
from local_service.worker import JobWorker


PNG_IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_lan_address_discovery_prefers_wifi_and_ignores_vpn_benchmark_ranges(monkeypatch):
    ifconfig_output = """utun6: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 4064
\tinet 198.18.0.1 --> 198.18.0.1 netmask 0xffffff00
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.31.89 netmask 0xffffff00 broadcast 192.168.31.255
bridge0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.64.1 netmask 0xffffff00
"""

    def run(command, **_kwargs):
        if command[0] == "ifconfig":
            return SimpleNamespace(stdout=ifconfig_output)
        return SimpleNamespace(stdout="interface: utun6\n")

    monkeypatch.setattr("local_service.capture_bridge.subprocess.run", run)
    addresses = discover_lan_ipv4_addresses()

    assert addresses[0] == {"ip": "192.168.31.89", "interface": "en0"}
    assert {item["ip"] for item in addresses} == {"192.168.31.89", "192.168.64.1"}


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


def make_roster(service, size=2):
    classroom = service.create_class("Capture Class")
    students = [
        service.create_student(classroom["id"], "{:03d}".format(index + 1), "Student {}".format(index + 1))
        for index in range(size)
    ]
    assignment = service.create_assignment(classroom["id"], "Worksheet", date.today().isoformat())
    return classroom, students, assignment


def upload(service, token, content=PNG_IMAGE, filename="page.png", upload_id=None, mime="image/png"):
    submission_id = service.current_capture(token)["current"]["submission_id"]
    return service.add_capture_uploaded_page(
        token, filename, mime, content, upload_id or str(uuid.uuid4()), submission_id
    )


def test_capture_session_stores_only_hashed_high_entropy_token_and_selects_roster_order(tmp_path):
    service = make_service(tmp_path)
    classroom, students, assignment = make_roster(service, size=2)
    session = service.start_capture_session(assignment["id"])

    assert len(session["token"]) >= 40
    with service.database.connection() as connection:
        stored = connection.execute(
            "SELECT token_hash, status FROM capture_sessions WHERE id = ?",
            (session["session_id"],),
        ).fetchone()
    assert stored["token_hash"] == hashlib.sha256(session["token"].encode("ascii")).hexdigest()
    assert stored["token_hash"] != session["token"]
    assert stored["status"] == "ACTIVE"
    state = service.current_capture(session["token"])
    assert state["class_name"] == classroom["name"]
    assert state["assignment_name"] == assignment["name"]
    assert state["current"]["student_id"] == students[0]["id"]
    assert state["current"]["status"] == "CAPTURING"
    assert state["current"]["page_count"] == 0


def test_invalid_expired_ended_and_restarted_sessions_reject_old_token(tmp_path):
    service = make_service(tmp_path)
    _, _, assignment = make_roster(service)
    session = service.start_capture_session(assignment["id"], expires_in_seconds=3600)

    with pytest.raises(Unauthorized):
        service.current_capture("wrong-token")

    with service.database.connection() as connection:
        connection.execute(
            "UPDATE capture_sessions SET expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", session["session_id"]),
        )
    assert service.capture_session_is_active(session["session_id"]) is False
    assert service.capture_admin_state()["status"] == "EXPIRED"
    with pytest.raises(Unauthorized):
        service.current_capture(session["token"])

    next_session = service.start_capture_session(assignment["id"])
    assert service.end_capture_session(next_session["session_id"])["status"] == "ENDED"
    with pytest.raises(Unauthorized):
        service.current_capture(next_session["token"])


def test_process_restart_expires_session_but_preserves_unfinished_submission(tmp_path):
    service = make_service(tmp_path)
    _, _, assignment = make_roster(service)
    session = service.start_capture_session(assignment["id"])
    database_path = service.database.path
    data_dir = service.data_dir

    restarted = MathGraderService(database_path, data_dir=data_dir)

    assert restarted.capture_admin_state()["status"] == "EXPIRED"
    with pytest.raises(Unauthorized):
        restarted.current_capture(session["token"])
    with restarted.database.connection() as connection:
        submission = connection.execute(
            "SELECT status FROM submissions WHERE id = ?",
            (session["current_submission_id"],),
        ).fetchone()
    assert submission["status"] == "CAPTURING"


def test_multpage_upload_metadata_idempotency_delete_and_reindex(tmp_path):
    service = make_service(tmp_path)
    _, students, assignment = make_roster(service)
    session = service.start_capture_session(assignment["id"])
    token = session["token"]
    upload_id = str(uuid.uuid4())

    first = upload(service, token, filename="../worksheet-1.png", upload_id=upload_id)
    repeated = upload(service, token, filename="different-name.png", upload_id=upload_id)
    second = upload(service, token, filename="worksheet-2.png")
    third = upload(service, token, filename="worksheet-3.png")

    assert first["page"]["id"] == repeated["page"]["id"]
    assert repeated["idempotent"] is True
    assert [first["page"]["page_index"], second["page"]["page_index"], third["page"]["page_index"]] == [1, 2, 3]
    assert first["page"]["original_filename"] == "worksheet-1.png"
    assert first["page"]["mime_type"] == "image/png"
    assert first["page"]["byte_size"] == len(PNG_IMAGE)
    assert first["page"]["uploaded_at"]
    assert (service.data_dir / first["page"]["source_ref"]).read_bytes() == PNG_IMAGE

    state = service.current_capture(token)
    assert state["current"]["page_count"] == 3
    assert [page["page_index"] for page in state["current"]["pages"]] == [1, 2, 3]

    updated = service.delete_capture_page(token, second["page"]["id"])
    assert updated["current"]["page_count"] == 2
    assert [page["page_index"] for page in updated["current"]["pages"]] == [1, 2]
    assert not (service.data_dir / second["page"]["source_ref"]).exists()

    other_submission = service.create_submission(assignment["id"], students[1]["id"])
    service.start_submission(other_submission["id"])
    unrelated = service.add_uploaded_page(other_submission["id"], "other.png", PNG_IMAGE)
    with pytest.raises(NotFound):
        service.capture_page_image(token, unrelated["id"])


def test_upload_rejects_empty_non_image_mime_mismatch_and_oversized_files(tmp_path):
    service = make_service(tmp_path)
    _, _, assignment = make_roster(service, size=1)
    session = service.start_capture_session(assignment["id"])

    with pytest.raises(ValidationError, match="empty"):
        upload(service, session["token"], content=b"")
    with pytest.raises(UnsupportedMediaType):
        upload(service, session["token"], content=b"this is text", mime="text/plain")
    with pytest.raises(UnsupportedMediaType, match="does not match"):
        upload(service, session["token"], content=PNG_IMAGE, mime="image/jpeg")
    with pytest.raises(PayloadTooLarge):
        upload(service, session["token"], content=b"\x89PNG\r\n\x1a\n" + b"x" * (10 * 1024 * 1024))

    assert service.current_capture(session["token"])["current"]["page_count"] == 0


def test_capture_page_path_traversal_is_rejected(tmp_path):
    service = make_service(tmp_path)
    _, students, assignment = make_roster(service, size=2)
    session = service.start_capture_session(assignment["id"])
    submission_id = session["current_submission_id"]
    page_id = str(uuid.uuid4())
    with service.database.connection() as connection:
        connection.execute(
            """INSERT INTO submission_pages
               (id, submission_id, page_index, source_ref, created_at, mime_type, byte_size)
               VALUES (?, ?, 1, 'pages/../../outside.png', ?, 'image/png', ?)""",
            (page_id, submission_id, "2026-01-01T00:00:00+00:00", len(PNG_IMAGE)),
        )
        connection.execute(
            "UPDATE submissions SET page_count = 1 WHERE id = ?", (submission_id,)
        )

    with pytest.raises(ValidationError, match="outside"):
        service.capture_page_image(session["token"], page_id)
    with pytest.raises(NotFound):
        service.delete_capture_page(session["token"], str(uuid.uuid4()))
    assert students[1]["id"] != service.current_capture(session["token"])["current"]["student_id"]


def test_finish_is_idempotent_advances_only_after_confirmation_and_allows_queue_overlap(tmp_path):
    entered_processing = threading.Event()
    release_processing = threading.Event()

    class SlowProvider:
        def recognize(self, source_ref, answer_type, context=None):
            entered_processing.set()
            release_processing.wait(3)
            return RecognitionResult(
                text="23", normalized_candidate="23", confidence=0.99,
                provider="test", model="slow-mock", latency_ms=100,
            )

    registry = ProviderRegistry()
    registry.register("slow", lambda name, settings: SlowProvider())
    config = {
        "recognition": {"default": {"primary": "slow-provider"}},
        "providers": {"slow-provider": {"type": "slow", "model": "slow-mock"}},
    }
    service = make_service(tmp_path, config=config, registry=registry)
    _, students, assignment = make_roster(service, size=2)
    session = service.start_capture_session(assignment["id"])
    token = session["token"]
    first_submission = session["current_submission_id"]
    assert service.current_capture(token)["current"]["student_id"] == students[0]["id"]

    first_page = upload(service, token)["page"]
    assert service.current_capture(token)["current"]["page_count"] == 1
    assert service.current_capture(token)["current"]["student_id"] == students[0]["id"]

    worker = JobWorker(service, poll_interval=0.01)
    worker.start()
    try:
        finished_first = service.finish_capture_submission(token, first_submission)
        assert finished_first["submission"]["status"] in {"QUEUED", "PROCESSING"}
        assert finished_first["already_finished"] is False
        assert finished_first["current"]["current"]["student_id"] == students[1]["id"]
        assert entered_processing.wait(2)

        second_submission = finished_first["current"]["current"]["submission_id"]
        assert service.get_submission(first_submission)["status"] == "PROCESSING"
        assert service.get_submission(second_submission)["status"] == "CAPTURING"
        with pytest.raises(InvalidTransition, match="current student"):
            service.add_capture_uploaded_page(
                token, "late.png", "image/png", PNG_IMAGE,
                str(uuid.uuid4()), first_submission,
            )
        second_page = upload(service, token)["page"]
        assert second_page["submission_id"] == second_submission
        assert first_page["submission_id"] == first_submission
        assert service.current_capture(token)["current"]["page_count"] == 1

        duplicate_first = service.finish_capture_submission(token, first_submission)
        assert duplicate_first["already_finished"] is True
        assert duplicate_first["current"]["current"]["submission_id"] == second_submission
        with service.database.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1

        release_processing.set()
        deadline = time.time() + 3
        while time.time() < deadline and service.get_submission(first_submission)["status"] != "COMPLETED":
            time.sleep(0.02)
        assert service.get_submission(first_submission)["status"] == "COMPLETED"

        finished_last = service.finish_capture_submission(token, second_submission)
        assert finished_last["submission"]["status"] in {"QUEUED", "PROCESSING", "COMPLETED"}
        assert finished_last["current"]["complete"] is True
        assert finished_last["current"]["current"] is None
        repeated_last = service.finish_capture_submission(token, second_submission)
        assert repeated_last["already_finished"] is True
        assert repeated_last["current"]["complete"] is True
        with service.database.connection() as connection:
            jobs = connection.execute(
                "SELECT submission_id, status FROM jobs ORDER BY sequence"
            ).fetchall()
        assert [row["submission_id"] for row in jobs] == [first_submission, second_submission]
        assert len({row["submission_id"] for row in jobs}) == 2
    finally:
        release_processing.set()
        worker.stop()


def request(method, url, json_body=None, body=None, headers=None):
    request_headers = dict(headers or {})
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=3) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            payload = json.loads(raw.decode("utf-8")) if "json" in content_type else raw
            return response.status, payload, response.headers
    except HTTPError as error:
        raw = error.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return error.code, payload, error.headers


def test_capture_http_surface_auth_host_origin_upload_delete_finish_and_end(tmp_path):
    service = make_service(tmp_path)
    _, students, assignment = make_roster(service, size=2)
    bridge = CaptureBridge(
        service,
        port=0,
        address_provider=lambda: [{"ip": "127.0.0.1", "interface": "loopback test"}],
    )
    admin = create_server(service, port=0, capture_bridge=bridge)
    admin_thread = threading.Thread(target=admin.serve_forever, daemon=True)
    admin_thread.start()
    admin_base = "http://127.0.0.1:{}".format(admin.server_address[1])
    token = None
    try:
        state = bridge.snapshot()
        assert state["status"] == "INACTIVE"
        assert bridge._server is None
        status, started, _ = request(
            "POST",
            admin_base + "/api/capture/session/start",
            json_body={"assignment_id": assignment["id"], "host": "127.0.0.1"},
        )
        assert status == 201
        assert started["status"] == "ACTIVE"
        assert "token_hash" not in started["session"]
        assert started["capture_url"].startswith("http://127.0.0.1:")
        token = urlsplit(started["capture_url"]).query.split("=", 1)[1]
        capture_base = "{}://{}:{}".format(
            urlsplit(started["capture_url"]).scheme,
            urlsplit(started["capture_url"]).hostname,
            urlsplit(started["capture_url"]).port,
        )

        page_status, html, page_headers = request("GET", started["capture_url"])
        assert page_status == 200
        assert b'capture="environment"' in html
        assert page_headers.get("Referrer-Policy") == "no-referrer"
        assert page_headers.get("Cache-Control") == "no-store"

        status, _, _ = request("GET", capture_base + "/api/capture/current")
        assert status == 401
        status, _, _ = request(
            "GET", capture_base + "/api/capture/current",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert status == 401
        status, _, _ = request(
            "GET", capture_base + "/api/capture/current",
            headers={"Authorization": "Bearer " + token, "Origin": "http://attacker.example"},
        )
        assert status == 403
        status, _, _ = request(
            "GET", capture_base + "/api/capture/current",
            headers={"Authorization": "Bearer " + token, "Host": "attacker.example"},
        )
        assert status == 403
        status, _, _ = request("GET", capture_base + "/api/classes")
        assert status == 404
        status, _, _ = request("POST", capture_base + "/api/capture/session/end")
        assert status == 404

        status, current, _ = request(
            "GET", capture_base + "/api/capture/current",
            headers={"Authorization": "Bearer " + token},
        )
        assert status == 200
        assert current["current"]["student_id"] == students[0]["id"]
        assert current["current"]["page_count"] == 0

        upload_id = str(uuid.uuid4())
        upload_headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "image/png",
            "X-File-Name": "%2E%2E%2Fworksheet.png",
            "X-Capture-Submission-ID": current["current"]["submission_id"],
            "Idempotency-Key": upload_id,
        }
        status, uploaded, _ = request(
            "POST", capture_base + "/api/capture/page", body=PNG_IMAGE, headers=upload_headers
        )
        assert status == 201
        assert uploaded["page"]["original_filename"] == "worksheet.png"
        assert uploaded["page"]["byte_size"] == len(PNG_IMAGE)
        status, repeated, _ = request(
            "POST", capture_base + "/api/capture/page", body=PNG_IMAGE, headers=upload_headers
        )
        assert status == 200 and repeated["idempotent"] is True
        assert repeated["page"]["id"] == uploaded["page"]["id"]

        status, _, _ = request(
            "POST", capture_base + "/api/capture/page", body=b"not an image",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "text/plain",
                "X-Capture-Submission-ID": current["current"]["submission_id"],
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert status == 415
        status, _, _ = request(
            "POST", capture_base + "/api/capture/page", body=b"",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "image/png",
                "X-Capture-Submission-ID": current["current"]["submission_id"],
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert status == 400
        status, _, _ = request(
            "POST", capture_base + "/api/capture/page", body=b"\x89PNG\r\n\x1a\n" + b"x" * (10 * 1024 * 1024),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "image/png",
                "X-Capture-Submission-ID": current["current"]["submission_id"],
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert status == 413

        status, image, headers = request(
            "GET", capture_base + "/api/capture/pages/{}/image".format(uploaded["page"]["id"]),
            headers={"Authorization": "Bearer " + token},
        )
        assert status == 200 and image == PNG_IMAGE
        assert headers.get("Content-Type") == "image/png"

        status, deleted, _ = request(
            "DELETE", capture_base + "/api/capture/pages/{}".format(uploaded["page"]["id"]),
            headers={"Authorization": "Bearer " + token},
        )
        assert status == 200 and deleted["current"]["page_count"] == 0
        assert service.current_capture(token)["current"]["student_id"] == students[0]["id"]

        status, uploaded_again, _ = request(
            "POST", capture_base + "/api/capture/page", body=PNG_IMAGE,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "image/png",
                "X-Capture-Submission-ID": current["current"]["submission_id"],
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert status == 201
        current_submission = current["current"]["submission_id"]
        status, finished, _ = request(
            "POST", capture_base + "/api/capture/submissions/{}/finish".format(current_submission),
            headers={"Authorization": "Bearer " + token},
        )
        assert status == 202
        assert finished["submission"]["status"] == "QUEUED"
        assert finished["current"]["current"]["student_id"] == students[1]["id"]

        status, _, _ = request(
            "GET", capture_base + "/api/capture/current",
            headers={"Authorization": "Bearer " + token},
        )
        assert status == 200
        assert request("GET", admin_base + "/health")[0] == 200

        status, ended, _ = request("POST", admin_base + "/api/capture/session/end", json_body={})
        assert status == 200 and ended["status"] == "ENDED"
        assert bridge._server is None
        with pytest.raises(Unauthorized):
            service.current_capture(token)
        with pytest.raises((URLError, OSError)):
            urlopen(started["capture_url"], timeout=1)
    finally:
        bridge.close()
        admin.shutdown()
        admin.server_close()
        admin_thread.join(timeout=2)


def test_admin_service_refuses_non_loopback_binding(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValueError, match="loopback"):
        create_server(service, host="0.0.0.0", port=0)


def test_capture_listener_closes_when_session_expires(tmp_path):
    service = make_service(tmp_path)
    _, _, assignment = make_roster(service, size=1)
    bridge = CaptureBridge(
        service,
        port=0,
        address_provider=lambda: [{"ip": "127.0.0.1", "interface": "loopback test"}],
    )
    try:
        active = bridge.start(assignment["id"], "127.0.0.1")
        assert active["status"] == "ACTIVE"
        session_id = active["session"]["id"]
        with service.database.connection() as connection:
            connection.execute(
                "UPDATE capture_sessions SET expires_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", session_id),
            )
        deadline = time.time() + 3
        while time.time() < deadline and bridge._server is not None:
            time.sleep(0.02)
        assert bridge._server is None
        assert service.capture_admin_state()["status"] == "EXPIRED"
    finally:
        bridge.close()
