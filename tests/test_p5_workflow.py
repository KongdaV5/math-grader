"""P5 teacher workflow vertical slice using local synthetic pages and provider doubles."""
import json
import io
import threading
import uuid
from urllib.request import Request, urlopen

import pytest
from PIL import Image, ImageDraw

from local_service.recognition import RecognitionResult
from local_service.http_server import create_server
from local_service.service import MathGraderService


def _service(path):
    return MathGraderService(path / "data" / "math-grader.sqlite3", data_dir=path / "data")


def _page_bytes(number):
    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.text((65, 75), "Synthetic Math Exam", fill="black")
    draw.text((65, 175), "{}. Calculate 7 + 5 = ______".format(number), fill="black")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class WorkflowProvider:
    def __init__(self, model_id, analysis_calls, uncertain_submissions):
        self.model_id = model_id
        self.analysis_calls = analysis_calls
        self.uncertain_submissions = uncertain_submissions

    def execute(self, request):
        if request.capability == "vision":
            page_index = request.context["page_index"]
            self.analysis_calls.append(page_index)
            payload = {"page_index": page_index, "questions": [{
                "question_no": "{}".format(page_index),
                "question_text": "Calculate 7 + 5",
                "answer_type": "integer",
                "answer_region": {"x": 0.08, "y": 0.18, "width": 0.82, "height": 0.18},
                "answer_key_candidate": "12",
                "accepted_answers": [], "score": 2,
                "confidence": 0.92, "analysis_note": "Synthetic fixture proposal",
            }]}
            text = json.dumps(payload)
            return RecognitionResult(text=text, confidence=0.92, provider="mlx_vlm",
                                     model=self.model_id, latency_ms=2,
                                     metadata={"fixture_provider": True})
        confidence = 0.35 if request.context.get("submission_id") in self.uncertain_submissions and request.context.get("question_no") == "2" else 0.99
        return RecognitionResult(text="12", confidence=confidence, provider="ppocr_onnx",
                                 model=self.model_id, latency_ms=1,
                                 metadata={"fixture_provider": True})


def _install_provider_doubles(service, analysis_calls, uncertain_submissions):
    service.model_manager.get_model_status = lambda model_id: {"state": "INSTALLED", "path": "fixture"}
    service.gateway.model_registry.get = lambda model_id: WorkflowProvider(model_id, analysis_calls, uncertain_submissions)


def _create_assignment(service):
    classroom = service.create_class("Synthetic E2E")
    first = service.create_student(classroom["id"], "A", "Student A")
    second = service.create_student(classroom["id"], "B", "Student B")
    assignment = service.create_assignment(classroom["id"], "Four-page exam", "2026-09-26",
                                           workflow_mode="TEACHER_WORKFLOW")
    return assignment, first, second


def _capture_submission(service, assignment, student, page_count=4):
    submission = service.create_submission(assignment["id"], student["id"])
    service.start_submission(submission["id"])
    for index in range(1, page_count + 1):
        service.add_uploaded_page(submission["id"], "page-{}.png".format(index), _page_bytes(index))
    finished = service.finish_submission(submission["id"])
    assert finished["status"] == "READY"
    return finished


def _run_queued_jobs(service):
    for _ in range(30):
        if not service.process_next_job():
            break


def test_student_a_four_pages_and_student_b_reuses_confirmed_exam_template(tmp_path):
    service = _service(tmp_path)
    analysis_calls = []
    uncertain_submissions = set()
    _install_provider_doubles(service, analysis_calls, uncertain_submissions)
    assignment, first, second = _create_assignment(service)

    student_a = _capture_submission(service, assignment, first)
    draft = service.teacher_workflow.analyze_exam(assignment["id"], student_a["id"])
    assert analysis_calls == [1, 2, 3, 4]
    assert draft["status"] == "DRAFT"
    assert len(draft["draft"]["pages"]) == 4
    assert all(page["questions"][0]["answer_region"] for page in draft["draft"]["pages"])
    confirmed = service.teacher_workflow.confirm_exam(assignment["id"])
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["temporary_template_created"] is True
    assert len(service.templates.list_page_templates(confirmed["template_group_id"])) == 4

    service.teacher_workflow.enqueue_grading(student_a["id"])
    _run_queued_jobs(service)
    graded_a = service.teacher_workflow.grade_result(student_a["id"])
    assert graded_a["submission"]["status"] == "COMPLETED", graded_a["job"]
    assert graded_a["submission"]["score"] == 8
    assert graded_a["submission"]["max_score"] == 8
    assert [result["decision_status"] for result in graded_a["question_results"]] == ["CORRECT"] * 4
    assert len(graded_a["submission"]["pages"]) == 4

    student_b = _capture_submission(service, assignment, second)
    uncertain_submissions.add(student_b["id"])
    assert service.teacher_workflow.get_exam_template(assignment["id"])["status"] == "CONFIRMED"
    service.teacher_workflow.enqueue_grading(student_b["id"])
    _run_queued_jobs(service)
    graded_b = service.teacher_workflow.grade_result(student_b["id"])
    assert analysis_calls == [1, 2, 3, 4], "a later Student must reuse the Assignment template"
    assert graded_b["submission"]["status"] == "REVIEW_REQUIRED"
    assert sum(result["decision_status"] == "REVIEW_REQUIRED" for result in graded_b["question_results"]) == 1
    pending = next(result for result in graded_b["question_results"] if result["review_status"] == "PENDING")
    reviewed = service.teacher_workflow.review_question(pending["id"], "CORRECT", "12")
    assert reviewed["submission"]["status"] == "COMPLETED"
    assert reviewed["submission"]["score"] == 8
    assert all(result["review_status"] == "DONE" for result in reviewed["question_results"]
               if result["decision_status"] == "CORRECT" and result["rule_code"] == "TEACHER_REVIEW")


def test_teacher_capture_finish_exposes_pages_without_legacy_submission_job(tmp_path):
    service = _service(tmp_path)
    assignment, first, second = _create_assignment(service)
    session = service.start_capture_session(assignment["id"])
    page = service.add_capture_uploaded_page(session["token"], "phone-page.png", "image/png",
        _page_bytes(1), str(uuid.uuid4()), session["current_submission_id"])["page"]
    finished = service.finish_capture_submission(session["token"], session["current_submission_id"])
    assert finished["submission"]["status"] == "READY"
    assert finished["submission"]["pages"][0]["id"] == page["id"]
    assert finished["current"]["current"]["student_id"] == second["id"]
    with service.database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs WHERE submission_id=?",
                                  (finished["submission"]["id"],)).fetchone()[0] == 0
    mime, content = service.slice.image_bytes("original", page["id"])
    assert mime == "image/png"
    assert content.startswith(b"\x89PNG")


def test_existing_workbook_can_be_selected_and_used_in_teacher_flow(tmp_path):
    service = _service(tmp_path)
    analysis_calls = []
    _install_provider_doubles(service, analysis_calls, set())
    assignment, student, _ = _create_assignment(service)
    group = service.templates.create_template_group("Known worksheet", "4", "fall", "Math book")
    template_page = service.templates.create_page_template(group["id"], 1, "Page 1")
    question = service.templates.create_question(template_page["id"], "1", "integer", "12", score=2)
    service.templates.create_answer_region(question["id"], 1, 0.08, 0.18, 0.82, 0.18)
    formula = service.templates.create_question(template_page["id"], "2", "formula", "12", score=1)
    service.templates.create_answer_region(formula["id"], 1, 0.08, 0.42, 0.82, 0.18)
    draft = service.teacher_workflow.choose_library_template(assignment["id"], group["id"])
    assert draft["draft"]["pages"][0]["questions"][0]["answer_key_candidate"] == "12"
    confirmed = service.teacher_workflow.confirm_exam(assignment["id"])
    assert confirmed["template_group_id"] == group["id"]
    assert confirmed["temporary_template_created"] is False
    submission = _capture_submission(service, assignment, student, page_count=1)
    service.teacher_workflow.enqueue_grading(submission["id"])
    _run_queued_jobs(service)
    result = service.teacher_workflow.grade_result(submission["id"])
    assert result["submission"]["status"] == "COMPLETED"
    assert result["submission"]["score"] == 3
    assert analysis_calls == []
    with service.database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM recognition_results WHERE model='pp-formulanet-plus-m'").fetchone()[0] == 1


def test_legacy_assignment_can_switch_before_capture_only(tmp_path):
    service = _service(tmp_path)
    classroom = service.create_class("Mode migration")
    student = service.create_student(classroom["id"], "1", "Student")
    assignment = service.create_assignment(classroom["id"], "Existing assignment", "2026-09-26")
    switched = service.teacher_workflow.enable_assignment(assignment["id"])
    assert switched["workflow_mode"] == "TEACHER_WORKFLOW"
    legacy = service.create_assignment(classroom["id"], "Started legacy assignment", "2026-09-26")
    submission = service.create_submission(legacy["id"], student["id"])
    service.start_submission(submission["id"])
    with pytest.raises(ValueError, match="already has capture activity"):
        service.teacher_workflow.enable_assignment(legacy["id"])


def test_teacher_exam_and_grading_api_routes_include_original_photos(tmp_path):
    service = _service(tmp_path)
    analysis_calls = []
    _install_provider_doubles(service, analysis_calls, set())
    assignment, student, _ = _create_assignment(service)
    submission = _capture_submission(service, assignment, student, page_count=1)
    server = create_server(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:{}".format(server.server_port)

    def request(path, method="GET", body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(base + path, data=data, method=method,
                      headers={"Content-Type": "application/json"} if data else {})
        with urlopen(req, timeout=5) as response:
            raw = response.read()
            if response.headers.get_content_type() == "application/json":
                return json.loads(raw)
            return raw

    try:
        original = request("/api/images/original/{}".format(submission["pages"][0]["id"]))
        assert original.startswith(b"\x89PNG")
        assert request("/api/assignments/{}/exam-template".format(assignment["id"])) is None
        draft = request("/api/assignments/{}/exam-template/analyze".format(assignment["id"]), "POST",
                        {"submission_id": submission["id"]})
        assert draft["status"] == "DRAFT"
        changed = draft["draft"]
        changed["pages"][0]["questions"][0]["answer_key_candidate"] = "12"
        request("/api/assignments/{}/exam-template".format(assignment["id"]), "PATCH", changed)
        confirmed = request("/api/assignments/{}/exam-template/confirm".format(assignment["id"]), "POST", {})
        assert confirmed["status"] == "CONFIRMED"
        queued = request("/api/submissions/{}/grade".format(submission["id"]), "POST", {})
        assert queued["status"] == "QUEUED"
        while service.process_next_job():
            pass
        result = request("/api/submissions/{}/grade".format(submission["id"]))
        assert result["submission"]["status"] == "COMPLETED"
        assert result["submission"]["score"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
