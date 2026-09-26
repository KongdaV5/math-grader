#!/usr/bin/env python3
"""Seed an isolated, synthetic profile for native P5-L2 UI acceptance only."""

import argparse
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

from local_service.recognition import RecognitionResult
from local_service.runtime_paths import RuntimePaths
from local_service.service import MathGraderService


FIXTURE_PREFIX = "math-grader-p5-native-gate-"
FIXTURE_PROVIDER = "native_gate_fixture"
FIXTURE_MODEL = "native-gate-fixture-provider"


def _safe_empty_fixture_root(value):
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise SystemExit("Fixture root must be an absolute path under /tmp")
    root = root.resolve()
    temp_root = Path("/tmp").resolve()
    if not root.is_relative_to(temp_root) or not root.name.startswith(FIXTURE_PREFIX):
        raise SystemExit("Refusing to write outside an explicitly named /tmp native gate fixture root")
    if root.exists() and any(root.iterdir()):
        raise SystemExit("Fixture root must be new or empty: {}".format(root))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _page_bytes(page_number, answer):
    image = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 80), "Synthetic Math Exam · Native Gate Fixture", fill="black")
    draw.text((70, 190), "Student work sample page {}".format(page_number), fill="black")
    draw.text((70, 320), "{}. Calculate 7 + 5 =".format(page_number), fill="black")
    draw.line((520, 770, 810, 770), fill="black", width=3)
    draw.text((550, 715), str(answer), fill="black")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class NativeGateFixtureProvider:
    """Deterministic provider double; it performs no model inference."""

    def __init__(self, answers_by_submission, analysis_calls):
        self.answers_by_submission = answers_by_submission
        self.analysis_calls = analysis_calls

    def execute(self, request):
        if request.capability == "vision":
            page_index = request.context["page_index"]
            self.analysis_calls.append(page_index)
            result = {"page_index": page_index, "questions": [{
                "question_no": str(page_index),
                "question_text": "Calculate 7 + 5",
                "answer_type": "integer",
                "answer_region": {"x": 0.56, "y": 0.56, "width": 0.36, "height": 0.22},
                "answer_key_candidate": "12",
                "accepted_answers": [],
                "score": 2,
                "confidence": 0.96,
                "analysis_note": "Synthetic fixture proposal; no Qwen inference was run.",
            }]}
            return RecognitionResult(
                text=json.dumps(result), confidence=0.96, provider=FIXTURE_PROVIDER,
                model=FIXTURE_MODEL, latency_ms=1,
                metadata={"fixture_only": True, "inference_performed": False},
            )

        submission_id = request.context["submission_id"]
        question_no = request.context["question_no"]
        text, confidence = self.answers_by_submission[submission_id][question_no]
        return RecognitionResult(
            text=text, confidence=confidence, provider=FIXTURE_PROVIDER,
            model=FIXTURE_MODEL, latency_ms=1,
            metadata={"fixture_only": True, "inference_performed": False},
        )


def _capture_submission(service, assignment_id, student_id, answer_by_page):
    submission = service.create_submission(assignment_id, student_id)
    service.start_submission(submission["id"])
    for page_number, answer in enumerate(answer_by_page, 1):
        service.add_uploaded_page(
            submission["id"], "synthetic-page-{}.png".format(page_number),
            _page_bytes(page_number, answer),
        )
    finished = service.finish_submission(submission["id"])
    if finished["status"] != "READY":
        raise RuntimeError("Teacher workflow fixture submission did not finish as READY")
    return finished


def _run_queued_jobs(service):
    processed = 0
    while service.process_next_job():
        processed += 1
        if processed > 20:
            raise RuntimeError("Fixture queued too many jobs")
    return processed


def seed(root):
    os.environ["MATH_GRADER_DATA_DIR"] = str(root)
    os.environ["MATH_GRADER_MODELS_DIR"] = str(root / "models")
    paths = RuntimePaths(root).ensure()
    service = MathGraderService(paths.database, data_dir=root)

    classroom = service.create_class("P5 Native Gate Test")
    student_a = service.create_student(classroom["id"], "A", "Student A")
    student_b = service.create_student(classroom["id"], "B", "Student B")
    student_c = service.create_student(classroom["id"], "C", "Entry Preview Student")

    today = date.today()
    workflow_assignment = service.create_assignment(
        classroom["id"], "P5 Native Workflow Smoke", today.isoformat(),
        workflow_mode="TEACHER_WORKFLOW",
    )
    entry_assignment = service.create_assignment(
        classroom["id"], "P5 Native Entry Smoke", (today - timedelta(days=1)).isoformat(),
        workflow_mode="TEACHER_WORKFLOW",
    )

    library = service.templates.create_template_group(
        "P5 Native Gate Sample Book", "4", "Synthetic", "Native Gate Fixture",
    )
    library_page = service.templates.create_page_template(library["id"], 1, "Synthetic sample page")
    library_question = service.templates.create_question(
        library_page["id"], "1", "integer", "12", score=2,
        metadata={"question_text": "Calculate 7 + 5"},
    )
    service.templates.create_answer_region(library_question["id"], 1, 0.56, 0.56, 0.36, 0.22)

    entry_submission = _capture_submission(
        service, entry_assignment["id"], student_c["id"], ["12"],
    )
    workflow_a = _capture_submission(
        service, workflow_assignment["id"], student_a["id"], ["12", "9", "11", "12"],
    )
    workflow_b = _capture_submission(
        service, workflow_assignment["id"], student_b["id"], ["12", "12", "12", "12"],
    )

    analysis_calls = []
    answers_by_submission = {
        workflow_a["id"]: {
            "1": ("12", 0.99),
            "2": ("9", 0.99),
            "3": ("11", 0.42),
            "4": ("12", 0.99),
        },
        workflow_b["id"]: {str(number): ("12", 0.99) for number in range(1, 5)},
    }
    service.model_manager.get_model_status = lambda model_id: {
        "state": "INSTALLED", "path": str(root / "models" / ("fixture-" + model_id)),
    }
    fixture_provider = NativeGateFixtureProvider(answers_by_submission, analysis_calls)
    service.gateway.model_registry.get = lambda _model_id: fixture_provider

    draft = service.teacher_workflow.analyze_exam(workflow_assignment["id"], workflow_a["id"])
    if analysis_calls != [1, 2, 3, 4]:
        raise RuntimeError("Fixture expected one provider-double analysis call per Student A page")
    if draft["analysis_metadata"].get("provider") != FIXTURE_PROVIDER:
        raise RuntimeError("Exam draft metadata did not preserve fixture provider provenance")
    confirmed = service.teacher_workflow.confirm_exam(workflow_assignment["id"])
    if confirmed["status"] != "CONFIRMED" or not confirmed["temporary_template_created"]:
        raise RuntimeError("Fixture did not create and confirm the Assignment temporary template")

    service.teacher_workflow.enqueue_grading(workflow_a["id"])
    _run_queued_jobs(service)
    result_a = service.teacher_workflow.grade_result(workflow_a["id"])
    if result_a["submission"]["status"] != "REVIEW_REQUIRED" or result_a["submission"]["score"] is not None:
        raise RuntimeError("Student A must have pending review and no official score before teacher review")
    decisions_a = [row["decision_status"] for row in result_a["question_results"]]
    if "CORRECT" not in decisions_a or "INCORRECT" not in decisions_a or "REVIEW_REQUIRED" not in decisions_a:
        raise RuntimeError("Student A fixture must include correct, incorrect, and pending review results")

    service.teacher_workflow.enqueue_grading(workflow_b["id"])
    _run_queued_jobs(service)
    result_b = service.teacher_workflow.grade_result(workflow_b["id"])
    if result_b["submission"]["status"] != "COMPLETED" or result_b["submission"]["score"] != 8:
        raise RuntimeError("Student B must complete using the confirmed Assignment template")
    if analysis_calls != [1, 2, 3, 4]:
        raise RuntimeError("Student B unexpectedly triggered a second full exam analysis")

    with service.database.connection() as connection:
        recognition_runs = connection.execute(
            "SELECT COUNT(*) FROM recognition_results WHERE provider=? AND model=?",
            (FIXTURE_PROVIDER, FIXTURE_MODEL),
        ).fetchone()[0]
    summary = {
        "fixture_only": True,
        "provider": FIXTURE_PROVIDER,
        "model": FIXTURE_MODEL,
        "inference_performed": False,
        "data_root": str(root),
        "class": {"id": classroom["id"], "name": classroom["name"]},
        "workflow_assignment": {"id": workflow_assignment["id"], "name": workflow_assignment["name"]},
        "entry_assignment": {"id": entry_assignment["id"], "name": entry_assignment["name"]},
        "students": [student_a["name"], student_b["name"], student_c["name"]],
        "submissions": {
            "student_a": {"id": workflow_a["id"], "pages": 4,
                          "status": result_a["submission"]["status"], "score": result_a["submission"]["score"],
                          "decision_statuses": decisions_a},
            "student_b": {"id": workflow_b["id"], "pages": 4,
                          "status": result_b["submission"]["status"], "score": result_b["submission"]["score"]},
            "entry_preview": {"id": entry_submission["id"], "pages": 1, "status": entry_submission["status"]},
        },
        "temporary_template": {"confirmed": True, "created_once_for_assignment": True,
                                "student_b_reused_without_reanalysis": True},
        "student_a_exam_analysis_page_calls": analysis_calls,
        "recognition_runs": recognition_runs,
        "expected_manual_review": {"question_no": "3", "student_answer": "11", "expected_answer": "12"},
    }
    (root / "fixture-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path, help="new empty /tmp/math-grader-p5-native-gate-... directory")
    args = parser.parse_args()
    root = _safe_empty_fixture_root(args.data_root)
    summary = seed(root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
