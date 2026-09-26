"""Teacher-facing exam setup, template reuse, deterministic grading and review."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
import re
import time
import uuid

from local_service.answer_normalizer import normalize_answer
from local_service.model_providers import RecognitionRequest
from local_service.templates import ANSWER_TYPES, validate_bbox


QWEN_MODEL_ID = "qwen3-vl-4b-mlx-4bit"
ANALYSIS_PROMPT_VERSION = "p5-exam-structure-v1"
MIN_GRADING_CONFIDENCE = 0.75

ANALYSIS_PROMPT = """Analyze this complete photographed page of an elementary math exam. Return only one JSON object, no markdown.
Use this exact shape: {\"questions\": [{\"question_no\": \"1\", \"question_text\": \"...\", \"answer_type\": \"integer|decimal|choice|boolean|comparison_symbol|fraction|formula|short_text|sequence|multi_blank\", \"answer_region\": {\"x\": 0.1, \"y\": 0.2, \"width\": 0.3, \"height\": 0.1}, \"answer_key_candidate\": \"...\", \"accepted_answers\": [], \"score\": 1, \"confidence\": 0.0, \"analysis_note\": \"...\"}]}
Find every numbered question visible on the page. Coordinates are normalized fractions of the full page, with (0,0) at the top-left. The answer_region must surround the student's intended answer space, not the printed question text. Solve each question to propose an answer_key_candidate only when the problem is legible and the answer is unambiguous; otherwise use null and explain briefly. Never claim certainty when the page is unclear. Keep question numbers as printed. Confidence is your estimate of this page structure and region, from 0 to 1."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id():
    return str(uuid.uuid4())


def _json_object(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Qwen returned an empty exam analysis")
    source = text.strip()
    if source.startswith("```"):
        source = re.sub(r"^```(?:json)?\s*|\s*```$", "", source, flags=re.IGNORECASE)
    start, end = source.find("{"), source.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Qwen exam analysis did not contain a JSON object")
    try:
        value = json.loads(source[start:end + 1])
    except json.JSONDecodeError as error:
        raise ValueError("Qwen exam analysis returned invalid JSON: {}".format(error.msg)) from error
    if not isinstance(value, dict):
        raise ValueError("Qwen exam analysis must be a JSON object")
    return value


def _finite_score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Question score must be a nonnegative number")
    return float(value)


def _region(value, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, dict):
        raise ValueError("Each question needs an answer-region candidate")
    region = {key: value.get(key) for key in ("x", "y", "width", "height")}
    validate_bbox(region["x"], region["y"], region["width"], region["height"])
    return region


def _normalize_draft(value, expected_pages):
    pages = value.get("pages")
    if not isinstance(pages, list) or len(pages) != expected_pages:
        raise ValueError("Exam analysis must return one page structure for every submitted page")
    normalized = []
    seen_pages = set()
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("Every exam page entry must be an object")
        page_index = page.get("page_index")
        if isinstance(page_index, bool) or not isinstance(page_index, int) or not 1 <= page_index <= expected_pages:
            raise ValueError("Exam analysis returned an invalid page_index")
        if page_index in seen_pages:
            raise ValueError("Exam analysis returned a duplicate page_index")
        seen_pages.add(page_index)
        questions = page.get("questions")
        if not isinstance(questions, list):
            raise ValueError("Every exam page must contain a questions list")
        page_questions = []
        seen_questions = set()
        for question in questions:
            if not isinstance(question, dict):
                raise ValueError("Every question entry must be an object")
            question_no = question.get("question_no")
            answer_type = question.get("answer_type")
            question_text = question.get("question_text", "")
            answer_key = question.get("answer_key_candidate")
            accepted = question.get("accepted_answers", [])
            if not isinstance(question_no, str) or not question_no.strip():
                raise ValueError("Every question needs a question number")
            question_no = question_no.strip()
            if question_no in seen_questions:
                raise ValueError("Question numbers must be unique within a page")
            seen_questions.add(question_no)
            if answer_type not in ANSWER_TYPES:
                raise ValueError("Unsupported answer type: {}".format(answer_type))
            if not isinstance(question_text, str):
                raise ValueError("question_text must be text")
            if answer_key is not None and not isinstance(answer_key, str):
                raise ValueError("answer_key_candidate must be text or null")
            if not isinstance(accepted, list) or any(not isinstance(item, str) for item in accepted):
                raise ValueError("accepted_answers must be a list of strings")
            confidence = question.get("confidence")
            if confidence is not None and (isinstance(confidence, bool) or
                                            not isinstance(confidence, (int, float)) or
                                            not math.isfinite(confidence) or not 0 <= confidence <= 1):
                raise ValueError("Question confidence must be between 0 and 1")
            analysis_note = question.get("analysis_note", "")
            if not isinstance(analysis_note, str):
                raise ValueError("analysis_note must be text")
            page_questions.append({
                "question_no": question_no,
                "question_text": question_text.strip(),
                "answer_type": answer_type,
                "answer_region": _region(question.get("answer_region")),
                "answer_key_candidate": answer_key.strip() if isinstance(answer_key, str) else None,
                "accepted_answers": accepted,
                "score": _finite_score(question.get("score", 1)),
                "confidence": float(confidence) if confidence is not None else None,
                "analysis_note": analysis_note.strip(),
            })
        normalized.append({"page_index": page_index, "questions": page_questions})
    if len(seen_pages) != expected_pages:
        raise ValueError("Exam analysis did not cover all submitted pages")
    normalized.sort(key=lambda item: item["page_index"])
    if not any(page["questions"] for page in normalized):
        raise ValueError("No questions were detected. Retake clearer page photos before continuing.")
    return {"pages": normalized}


def _canonical_answer(answer, answer_type):
    if answer is None:
        return None
    normalized = normalize_answer(str(answer))["normalized"]
    if answer_type == "choice":
        normalized = normalized.upper()
    return " ".join(normalized.split())


class TeacherWorkflow:
    def __init__(self, service):
        self.service = service
        self.database = service.database

    def _assignment(self, assignment_id):
        with self.database.connection() as connection:
            row = self.service._require(connection, "assignments", assignment_id)
        return dict(row)

    def _require_teacher_mode(self, assignment_id):
        assignment = self._assignment(assignment_id)
        if assignment.get("workflow_mode") != "TEACHER_WORKFLOW":
            raise ValueError("Choose teacher workflow when creating this Assignment")
        return assignment

    def enable_assignment(self, assignment_id):
        assignment = self._assignment(assignment_id)
        if assignment.get("workflow_mode") == "TEACHER_WORKFLOW":
            return self.service._row(assignment)
        with self.database.connection() as connection:
            started = connection.execute("""SELECT COUNT(*) FROM submissions
                WHERE assignment_id=? AND status!='EMPTY'""", (assignment_id,)).fetchone()[0]
            active_session = connection.execute("""SELECT COUNT(*) FROM capture_sessions
                WHERE assignment_id=? AND status='ACTIVE'""", (assignment_id,)).fetchone()[0]
            if started or active_session:
                raise ValueError("Start a new Assignment before enabling the teacher workflow; this Assignment already has capture activity")
            connection.execute("UPDATE assignments SET workflow_mode='TEACHER_WORKFLOW' WHERE id=?",
                               (assignment_id,))
            row = connection.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
        return self.service._row(row)

    def get_exam_template(self, assignment_id):
        self._assignment(assignment_id)
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM assignment_exam_templates WHERE assignment_id=?", (assignment_id,)
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["draft"] = json.loads(item.pop("draft_json"))
            item["analysis_metadata"] = json.loads(item.pop("analysis_metadata_json"))
            if item["template_group_id"]:
                group = connection.execute("SELECT * FROM template_groups WHERE id=?",
                                           (item["template_group_id"],)).fetchone()
                item["template_group"] = self.service._row(group)
        return item

    def analyze_exam(self, assignment_id, submission_id):
        self._require_teacher_mode(assignment_id)
        submission = self.service.get_submission(submission_id)
        if submission["assignment_id"] != assignment_id:
            raise ValueError("Source Submission must belong to this Assignment")
        if submission["status"] == "CAPTURING":
            raise ValueError("Finish capturing all pages before analyzing the exam")
        if not submission["pages"]:
            raise ValueError("Capture at least one page before analyzing the exam")
        current = self.get_exam_template(assignment_id)
        if current and current["status"] == "CONFIRMED":
            raise ValueError("This Assignment already has a confirmed temporary template")
        if self.service.model_manager.get_model_status(QWEN_MODEL_ID)["state"] != "INSTALLED":
            raise ValueError("Install Qwen3-VL 4B in Model Center before analyzing a new exam")
        provider = self.service.gateway.model_registry.get(QWEN_MODEL_ID)
        analyzed_pages = []
        page_latencies = []
        for page in submission["pages"]:
            source = self.service._stored_page_path(page["source_ref"])
            if source is None or not source.is_file():
                raise ValueError("Source exam image is missing for page {}".format(page["page_index"]))
            started = time.perf_counter()
            result = provider.execute(RecognitionRequest(
                image=str(source), answer_type="vision", capability="vision",
                context={"assignment_id": assignment_id, "page_index": page["page_index"]},
                prompt=ANALYSIS_PROMPT,
                constraints={"max_tokens": 3072, "prompt_version": ANALYSIS_PROMPT_VERSION},
            ))
            raw = _json_object(result.text)
            analyzed_pages.append({"page_index": page["page_index"], "questions": raw.get("questions")})
            page_latencies.append({"page_index": page["page_index"],
                                   "latency_ms": int((time.perf_counter() - started) * 1000)})
        draft = _normalize_draft({"pages": analyzed_pages}, len(submission["pages"]))
        now = _now()
        metadata = {"provider": "mlx_vlm", "model": QWEN_MODEL_ID,
                    "prompt_version": ANALYSIS_PROMPT_VERSION, "page_count": len(submission["pages"]),
                    "page_latencies": page_latencies}
        with self.database.connection() as connection:
            existing = connection.execute("SELECT id, template_group_id, created_at FROM assignment_exam_templates WHERE assignment_id=?",
                                           (assignment_id,)).fetchone()
            if existing:
                connection.execute("""UPDATE assignment_exam_templates SET source_submission_id=?,status='DRAFT',
                    draft_json=?,analysis_metadata_json=?,updated_at=?,confirmed_at=NULL WHERE assignment_id=?""",
                    (submission_id, json.dumps(draft, ensure_ascii=False), json.dumps(metadata), now, assignment_id))
            else:
                connection.execute("""INSERT INTO assignment_exam_templates
                    (id,assignment_id,source_submission_id,status,draft_json,analysis_metadata_json,created_at,updated_at)
                    VALUES(?,?,?,'DRAFT',?,?,?,?)""",
                    (_id(), assignment_id, submission_id, json.dumps(draft, ensure_ascii=False),
                     json.dumps(metadata), now, now))
        return self.get_exam_template(assignment_id)

    def choose_library_template(self, assignment_id, group_id):
        self._require_teacher_mode(assignment_id)
        group = self.service.templates.get_template_group(group_id)
        listed = self.service.templates.list_page_templates(group_id)
        latest = {}
        for candidate in listed:
            if not candidate["active"]:
                continue
            current = latest.get(candidate["page_number"])
            if current is None or candidate["version"] > current["version"]:
                latest[candidate["page_number"]] = candidate
        pages = [self.service.templates.get_page_template(latest[number]["id"])
                 for number in sorted(latest)]
        if not pages:
            raise ValueError("The selected workbook has no page templates")
        if [page["page_number"] for page in pages] != list(range(1, len(pages) + 1)):
            raise ValueError("The selected workbook pages must use consecutive page numbers starting at 1")
        draft_pages = []
        for page in pages:
            questions = []
            for question in page["questions"]:
                metadata = question.get("metadata") or {}
                regions = question.get("regions") or []
                questions.append({
                    "question_no": question["question_no"],
                    "question_text": metadata.get("question_text", ""),
                    "answer_type": question["answer_type"],
                    "answer_region": ({key: regions[0][key] for key in ("x", "y", "width", "height")}
                                      if regions else None),
                    "answer_key_candidate": question["correct_answer"],
                    "accepted_answers": question["accepted_answers"],
                    "score": question["score"], "confidence": 1.0,
                    "analysis_note": "来自已有题册。",
                })
            draft_pages.append({"page_index": page["page_number"], "questions": questions})
        draft = _normalize_draft({"pages": draft_pages}, len(draft_pages))
        now = _now()
        metadata = {"source": "LIBRARY", "template_group_id": group_id,
                    "template_name": group["name"]}
        with self.database.connection() as connection:
            row = connection.execute("SELECT status FROM assignment_exam_templates WHERE assignment_id=?",
                                     (assignment_id,)).fetchone()
            if row and row["status"] == "CONFIRMED":
                raise ValueError("This Assignment already has a confirmed template")
            if row:
                connection.execute("""UPDATE assignment_exam_templates SET template_group_id=?,source_submission_id=NULL,
                    status='DRAFT',draft_json=?,analysis_metadata_json=?,updated_at=?,confirmed_at=NULL
                    WHERE assignment_id=?""",
                    (group_id, json.dumps(draft, ensure_ascii=False), json.dumps(metadata), now, assignment_id))
            else:
                connection.execute("""INSERT INTO assignment_exam_templates
                    (id,assignment_id,template_group_id,status,draft_json,analysis_metadata_json,created_at,updated_at)
                    VALUES(?,?,?,'DRAFT',?,?,?,?)""",
                    (_id(), assignment_id, group_id, json.dumps(draft, ensure_ascii=False),
                     json.dumps(metadata), now, now))
        return self.get_exam_template(assignment_id)

    def update_draft(self, assignment_id, payload):
        self._require_teacher_mode(assignment_id)
        if not isinstance(payload, dict):
            raise ValueError("Draft update must be an object")
        with self.database.connection() as connection:
            existing = connection.execute("SELECT * FROM assignment_exam_templates WHERE assignment_id=?",
                                          (assignment_id,)).fetchone()
        if existing is None or existing["status"] != "DRAFT":
            raise ValueError("There is no editable exam draft for this Assignment")
        draft = _normalize_draft(payload, len(json.loads(existing["draft_json"])["pages"]))
        with self.database.connection() as connection:
            connection.execute("UPDATE assignment_exam_templates SET draft_json=?,updated_at=? WHERE assignment_id=?",
                               (json.dumps(draft, ensure_ascii=False), _now(), assignment_id))
        return self.get_exam_template(assignment_id)

    def confirm_exam(self, assignment_id):
        assignment = self._require_teacher_mode(assignment_id)
        with self.database.connection() as connection:
            exam = connection.execute("SELECT * FROM assignment_exam_templates WHERE assignment_id=?",
                                      (assignment_id,)).fetchone()
        if exam is None or exam["status"] != "DRAFT":
            raise ValueError("Create or select an exam draft before confirming it")
        draft = _normalize_draft(json.loads(exam["draft_json"]), len(json.loads(exam["draft_json"])["pages"]))
        for page in draft["pages"]:
            for question in page["questions"]:
                _region(question["answer_region"], required=True)
        now = _now()
        group_id = exam["template_group_id"]
        created_group = False
        with self.database.connection() as connection:
            if group_id is None:
                source = self.service.get_submission(exam["source_submission_id"])
                class_row = connection.execute("SELECT c.name FROM classes c JOIN assignments a ON a.class_id=c.id WHERE a.id=?",
                                               (assignment_id,)).fetchone()
                group_id = _id()
                connection.execute("""INSERT INTO template_groups
                    (id,name,grade,semester,book_name,publisher,version,created_at,updated_at,assignment_id,temporary)
                    VALUES(?,?,?,?,?,NULL,1,?,?,?,1)""",
                    (group_id, assignment["name"] + " · 本次临时模板", "未指定", "本次测验",
                     assignment["name"], now, now, assignment_id))
                created_group = True
                page_by_index = {page["page_index"]: page for page in source["pages"]}
                for page_spec in draft["pages"]:
                    page_index = page_spec["page_index"]
                    source_page = page_by_index.get(page_index)
                    if source_page is None:
                        raise ValueError("Draft page {} has no source exam photo".format(page_index))
                    page_template_id = _id()
                    connection.execute("""INSERT INTO page_templates
                        (id,template_group_id,page_number,name,reference_image,version,active,created_at,updated_at)
                        VALUES(?,?,?,?,?,1,1,?,?)""",
                        (page_template_id, group_id, page_index, "第 {} 页".format(page_index),
                         source_page["source_ref"], now, now))
                    for question in page_spec["questions"]:
                        question_id = _id()
                        qmeta = {"question_text": question["question_text"],
                                 "analysis_note": question["analysis_note"],
                                 "candidate_confidence": question["confidence"]}
                        connection.execute("""INSERT INTO template_questions
                            (id,page_template_id,question_no,answer_type,correct_answer,accepted_answers_json,
                             score,knowledge_tag,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            (question_id, page_template_id, question["question_no"], question["answer_type"],
                             question["answer_key_candidate"], json.dumps(question["accepted_answers"]),
                             question["score"], None, json.dumps(qmeta, ensure_ascii=False), now))
                        region = question["answer_region"]
                        connection.execute("""INSERT INTO answer_regions
                            (id,question_id,region_index,x,y,width,height,coordinate_space,metadata_json,created_at)
                            VALUES(?,?,1,?,?,?,?, 'normalized', '{}', ?)""",
                            (_id(), question_id, region["x"], region["y"], region["width"], region["height"], now))
            connection.execute("""UPDATE assignment_exam_templates SET template_group_id=?,status='CONFIRMED',
                draft_json=?,updated_at=?,confirmed_at=? WHERE assignment_id=?""",
                (group_id, json.dumps(draft, ensure_ascii=False), now, now, assignment_id))
        result = self.get_exam_template(assignment_id)
        result["temporary_template_created"] = created_group
        return result

    def enqueue_grading(self, submission_id):
        submission = self.service.get_submission(submission_id)
        assignment_id = submission["assignment_id"]
        exam = self.get_exam_template(assignment_id)
        if not exam or exam["status"] != "CONFIRMED":
            raise ValueError("Confirm this Assignment's exam template before grading submissions")
        if submission["status"] not in ("READY", "FAILED"):
            raise ValueError("Only a captured Submission can start or retry grading")
        now = _now()
        with self.database.connection() as connection:
            self.service_transition(connection, submission_id, "QUEUED", now)
            job = connection.execute("SELECT id FROM jobs WHERE submission_id=? AND kind='GRADING'",
                                     (submission_id,)).fetchone()
            if job:
                connection.execute("""UPDATE jobs SET status='QUEUED',error=NULL,created_at=?,started_at=NULL,
                    completed_at=NULL WHERE id=?""", (now, job["id"]))
                job_id = job["id"]
            else:
                job_id = _id()
                connection.execute("INSERT INTO jobs(id,submission_id,status,created_at,kind) VALUES(?,?,'QUEUED',?,'GRADING')",
                                   (job_id, submission_id, now))
            connection.execute("DELETE FROM question_results WHERE submission_id=?", (submission_id,))
            connection.execute("UPDATE submissions SET score=NULL,max_score=NULL,review_completed_at=NULL WHERE id=?",
                               (submission_id,))
        return {"submission_id": submission_id, "job_id": job_id, "status": "QUEUED"}

    @staticmethod
    def service_transition(connection, submission_id, target, now):
        from local_service.state_machine import transition
        transition(connection, submission_id, target, now)

    def process_submission(self, submission_id):
        submission = self.service.get_submission(submission_id)
        exam = self.get_exam_template(submission["assignment_id"])
        if not exam or exam["status"] != "CONFIRMED":
            raise ValueError("Assignment exam template is not confirmed")
        page_templates = [self.service.templates.get_page_template(page["id"])
                          for page in self.service.templates.list_page_templates(exam["template_group_id"])]
        source_pages = {page["page_index"]: page for page in submission["pages"]}
        expected_pages = {page["page_number"]: page for page in page_templates}
        question_specs = []
        for template_page in page_templates:
            for question in template_page["questions"]:
                metadata = question.get("metadata") or {}
                question_specs.append((template_page["page_number"], question, metadata))
        question_by_page = {}
        for page_number, question, metadata in question_specs:
            question_by_page.setdefault(page_number, []).append((question, metadata))
        for page_number, specs in question_by_page.items():
            page = source_pages.get(page_number)
            if page is None:
                for question, metadata in specs:
                    self._save_question_result(submission_id, None, question, None, None,
                                               "REVIEW_REQUIRED", "MISSING_SUBMISSION_PAGE",
                                               {"page_number": page_number, "reason": "student page is missing"})
                continue
            detail = self.service.slice.page_detail(page["id"])
            if detail["page"]["processing_status"] not in ("READY", "WARNING") or not detail["page"]["processed_image"]:
                try:
                    self.service.slice.process_page(page["id"])
                except Exception as error:
                    for question, metadata in specs:
                        self._save_question_result(submission_id, page["id"], question, None, None,
                                                   "REVIEW_REQUIRED", "PAGE_PROCESSING_FAILED",
                                                   {"page_number": page_number, "error": str(error)[:300]})
                    continue
            self.service.slice.bind_template(page["id"], expected_pages[page_number]["id"])
            crops = self.service.slice.create_crops(page["id"])
            crops_by_question = {}
            for crop in crops:
                crops_by_question.setdefault(crop["question_id"], []).append(crop)
            for question, metadata in specs:
                crop_rows = crops_by_question.get(question["id"], [])
                if not crop_rows:
                    self._save_question_result(submission_id, page["id"], question, None, None,
                                               "REVIEW_REQUIRED", "NO_ANSWER_REGION",
                                               {"page_number": page_number})
                    continue
                recognized = [self._recognize_crop(submission_id, page["id"], crop) for crop in crop_rows]
                valid = [item for item in recognized if item["answer"] is not None]
                if len(recognized) == 1 and len(valid) == 1:
                    decision, awarded, rule = self._deterministic_decision(
                        question, valid[0]["answer"], valid[0]["confidence"])
                    self._save_question_result(submission_id, page["id"], question,
                                               valid[0]["run_id"], valid[0], decision, rule,
                                               {"page_number": page_number, "question_text": metadata.get("question_text", ""),
                                                "region_count": len(recognized)}, awarded)
                else:
                    self._save_question_result(submission_id, page["id"], question,
                                               valid[0]["run_id"] if valid else (recognized[0]["run_id"] if recognized else None),
                                               valid[0] if valid else recognized[0], "REVIEW_REQUIRED",
                                               "MULTIPLE_OR_UNREADABLE_REGIONS",
                                               {"page_number": page_number, "question_text": metadata.get("question_text", ""),
                                                "region_count": len(recognized),
                                                "recognition_errors": [item["error"] for item in recognized if item["error"]]},
                                               0.0)
        for page_number, page in source_pages.items():
            if page_number not in expected_pages:
                self._save_question_result(submission_id, page["id"], None, None, None,
                                           "REVIEW_REQUIRED", "UNMAPPED_SUBMISSION_PAGE",
                                           {"page_number": page_number, "reason": "no page in confirmed exam template"})
        return self._finalize_grading(submission_id)

    def _recognize_crop(self, submission_id, page_id, crop):
        route = self.service.slice.routes.get(crop["answer_type"], {})
        candidates = [route.get("primary"), route.get("fallback")]
        last_error = "No model route is configured for this answer type"
        for model_id in (item for item in candidates if item):
            status = self.service.model_manager.get_model_status(model_id)["state"]
            if status != "INSTALLED":
                last_error = "{} is not installed".format(model_id)
                continue
            provider = self.service.gateway.model_registry.get(model_id)
            prompt = ""
            try:
                if self.service.model_catalog.get(model_id)["provider_type"] == "mlx_vlm":
                    from local_service.vision_strategy import VisionRecognitionStrategy
                    prompt = VisionRecognitionStrategy.prompt(crop["answer_type"])
                result = provider.execute(RecognitionRequest(
                    image=str(self.service.paths.root / crop["crop_path"]),
                    answer_type=crop["answer_type"], capability=crop["answer_type"],
                    context={"submission_id": submission_id, "page_id": page_id,
                             "question_no": crop["question_no"]},
                    prompt=prompt, constraints={"max_tokens": 96},
                ))
                if prompt:
                    from local_service.vision_strategy import VisionRecognitionStrategy
                    normalized = VisionRecognitionStrategy.parse(crop["answer_type"], result.text)["normalized"]
                else:
                    normalized = normalize_answer(result.text)["normalized"]
                run_id = _id()
                metadata = dict(result.metadata)
                with self.database.connection() as connection:
                    connection.execute("""INSERT INTO recognition_results
                        (id,submission_id,page_id,crop_id,page_template_id,template_version,question_id,
                         answer_region_id,region_index,crop_path,provider,model,latency_ms,metadata_json,
                         created_at,status,text,normalized_candidate,confidence)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'SUCCESS',?,?,?)""",
                        (run_id, submission_id, page_id, crop["id"], crop["page_template_id"],
                         crop["template_version"], crop["question_id"], crop["answer_region_id"],
                         crop["region_index"], crop["crop_path"], result.provider, model_id,
                         result.latency_ms, json.dumps(metadata, ensure_ascii=False), _now(),
                         result.text, normalized, result.confidence))
                return {"run_id": run_id, "answer": normalized, "confidence": result.confidence,
                        "model": model_id, "error": None}
            except Exception as error:
                last_error = "{}: {}".format(model_id, str(error)[:250])
        run_id = _id()
        metadata = {"workflow": "P5", "recognition_error": last_error}
        with self.database.connection() as connection:
            connection.execute("""INSERT INTO recognition_results
                (id,submission_id,page_id,crop_id,page_template_id,template_version,question_id,
                 answer_region_id,region_index,crop_path,provider,model,latency_ms,metadata_json,
                 created_at,status,text,normalized_candidate,confidence,error,error_code,completed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'FAILED',NULL,NULL,NULL,?,?,?,?)""",
                (run_id, submission_id, page_id, crop["id"], crop["page_template_id"],
                 crop["template_version"], crop["question_id"], crop["answer_region_id"],
                 crop["region_index"], crop["crop_path"], "unavailable",
                 candidates[0] or "unconfigured", 0, json.dumps(metadata), _now(),
                 last_error, "PROVIDER_UNAVAILABLE", _now()))
        return {"run_id": run_id, "answer": None, "confidence": None,
                "model": candidates[0], "error": last_error}

    @staticmethod
    def _deterministic_decision(question, student_answer, confidence):
        expected = question["correct_answer"]
        accepted = question.get("accepted_answers")
        if accepted is None:
            accepted = json.loads(question.get("accepted_answers_json") or "[]")
        if not expected and not accepted:
            return "REVIEW_REQUIRED", 0.0, "ANSWER_KEY_MISSING"
        if student_answer is None or confidence is None or confidence < MIN_GRADING_CONFIDENCE:
            return "REVIEW_REQUIRED", 0.0, "LOW_RECOGNITION_CONFIDENCE"
        possible = [answer for answer in [expected] + accepted if answer is not None]
        student = _canonical_answer(student_answer, question["answer_type"])
        matches = any(student == _canonical_answer(answer, question["answer_type"]) for answer in possible)
        return ("CORRECT", float(question["score"]), "EXACT_NORMALIZED_MATCH") if matches else (
            "INCORRECT", 0.0, "EXACT_NORMALIZED_MISMATCH")

    def _save_question_result(self, submission_id, page_id, question, run_id, recognized,
                              decision, rule, evidence, awarded=None):
        question_id = question["id"] if question else None
        expected = question["correct_answer"] if question else None
        accepted = (question.get("accepted_answers") if question else [])
        if question is not None and accepted is None:
            accepted = json.loads(question.get("accepted_answers_json") or "[]")
        answer = recognized["answer"] if recognized else None
        confidence = recognized["confidence"] if recognized else None
        maximum = float(question["score"]) if question else 0.0
        if awarded is None:
            awarded = maximum if decision == "CORRECT" else 0.0
        with self.database.connection() as connection:
            connection.execute("""INSERT OR REPLACE INTO question_results
                (id,submission_id,page_id,template_question_id,question_no,answer_type,recognition_result_id,
                 expected_answer,accepted_answers_json,student_answer,confidence,decision_status,review_status,
                 reviewed_answer,awarded_score,max_score,rule_code,evidence_json,created_at,reviewed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,NULL)""",
                (_id(), submission_id, page_id, question_id,
                 question["question_no"] if question else str((evidence or {}).get("page_number", "?")),
                 question["answer_type"] if question else "unmapped", run_id, expected,
                 json.dumps(accepted), answer, confidence, decision,
                 "PENDING" if decision == "REVIEW_REQUIRED" else "DONE", float(awarded), maximum,
                 rule, json.dumps(evidence or {}, ensure_ascii=False), _now()))

    def _finalize_grading(self, submission_id):
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM question_results WHERE submission_id=? ORDER BY question_no,id",
                                      (submission_id,)).fetchall()
            pending = any(row["decision_status"] == "REVIEW_REQUIRED" for row in rows)
            max_score = sum(float(row["max_score"]) for row in rows)
            if pending:
                from local_service.state_machine import transition
                transition(connection, submission_id, "REVIEW_REQUIRED", _now())
                connection.execute("UPDATE submissions SET score=NULL,max_score=? WHERE id=?", (max_score, submission_id))
            else:
                score = sum(float(row["awarded_score"]) for row in rows)
                from local_service.state_machine import transition
                transition(connection, submission_id, "COMPLETED", _now())
                connection.execute("UPDATE submissions SET score=?,max_score=?,review_completed_at=? WHERE id=?",
                                   (score, max_score, _now(), submission_id))
        return self.grade_result(submission_id)

    def grade_result(self, submission_id):
        submission = self.service.get_submission(submission_id)
        with self.database.connection() as connection:
            results = [dict(row) for row in connection.execute(
                "SELECT * FROM question_results WHERE submission_id=? ORDER BY question_no,id", (submission_id,))]
            job = connection.execute("SELECT * FROM jobs WHERE submission_id=? AND kind='GRADING'",
                                     (submission_id,)).fetchone()
        for result in results:
            result["accepted_answers"] = json.loads(result.pop("accepted_answers_json"))
            result["evidence"] = json.loads(result.pop("evidence_json"))
        return {"submission": submission, "question_results": results,
                "job": dict(job) if job else None}

    def review_queue(self):
        with self.database.connection() as connection:
            rows = connection.execute("""SELECT s.id AS submission_id,s.score,s.max_score,s.status,
                st.name AS student_name,st.student_no,a.name AS assignment_name,a.id AS assignment_id
                FROM submissions s JOIN students st ON st.id=s.student_id
                JOIN assignments a ON a.id=s.assignment_id WHERE s.status='REVIEW_REQUIRED'
                ORDER BY s.finished_capture_at,s.id""").fetchall()
        return [self.grade_result(row["submission_id"]) | {
            "student_name": row["student_name"], "student_no": row["student_no"],
            "assignment_name": row["assignment_name"], "assignment_id": row["assignment_id"]
        } for row in rows]

    def review_question(self, result_id, decision, reviewed_answer=None):
        if decision not in ("CORRECT", "INCORRECT"):
            raise ValueError("Review decision must be CORRECT or INCORRECT")
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM question_results WHERE id=?", (result_id,)).fetchone()
            if row is None:
                raise KeyError("QuestionResult not found")
            if row["review_status"] == "DONE":
                raise ValueError("This QuestionResult has already been reviewed")
            answer = reviewed_answer if isinstance(reviewed_answer, str) else row["student_answer"]
            awarded = float(row["max_score"]) if decision == "CORRECT" else 0.0
            connection.execute("""UPDATE question_results SET decision_status=?,review_status='DONE',
                reviewed_answer=?,awarded_score=?,rule_code='TEACHER_REVIEW',reviewed_at=? WHERE id=?""",
                (decision, answer, awarded, _now(), result_id))
            remaining = connection.execute("SELECT COUNT(*) FROM question_results WHERE submission_id=? AND review_status='PENDING'",
                                           (row["submission_id"],)).fetchone()[0]
            if remaining == 0:
                totals = connection.execute("SELECT SUM(awarded_score),SUM(max_score) FROM question_results WHERE submission_id=?",
                                            (row["submission_id"],)).fetchone()
                from local_service.state_machine import transition
                transition(connection, row["submission_id"], "COMPLETED", _now())
                connection.execute("UPDATE submissions SET score=?,max_score=?,review_completed_at=? WHERE id=?",
                                   (float(totals[0] or 0), float(totals[1] or 0), _now(), row["submission_id"]))
        return self.grade_result(row["submission_id"])
