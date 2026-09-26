import base64
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from local_service.database import Database
from local_service.recognition import RecognitionGateway
from local_service.state_machine import InvalidTransition, transition


class NotFound(LookupError):
    pass


class ValidationError(ValueError):
    pass


class ProcessingError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id():
    return str(uuid.uuid4())


class MathGraderService:
    def __init__(self, database_path, data_dir=None, recognition_config=None, registry=None):
        self.database = Database(database_path)
        self.data_dir = Path(data_dir) if data_dir else Path(database_path).parent
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir = self.data_dir / "pages"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.gateway = RecognitionGateway.from_file(recognition_config, registry=registry)
        self.recover_interrupted_jobs()

    def health(self):
        with self.database.connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "service": "math-grader-local"}

    def list_classes(self):
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM classes ORDER BY name, id").fetchall()
        return [self._row(row) for row in rows]

    def create_class(self, name):
        name = self._required_text(name, "name")
        item = {"id": new_id(), "name": name, "active": True, "created_at": utc_now()}
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO classes (id, name, active, created_at) VALUES (?, ?, 1, ?)",
                (item["id"], item["name"], item["created_at"]),
            )
        return item

    def list_students(self, class_id):
        with self.database.connection() as connection:
            self._require(connection, "classes", class_id)
            rows = connection.execute(
                "SELECT * FROM students WHERE class_id = ? ORDER BY student_no, id", (class_id,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def create_student(self, class_id, student_no, name):
        student_no = self._required_text(student_no, "student_no")
        name = self._required_text(name, "name")
        item = {
            "id": new_id(), "class_id": class_id, "student_no": student_no,
            "name": name, "active": True, "created_at": utc_now(),
        }
        try:
            with self.database.connection() as connection:
                self._require(connection, "classes", class_id)
                connection.execute(
                    """INSERT INTO students
                       (id, class_id, student_no, name, active, created_at)
                       VALUES (?, ?, ?, ?, 1, ?)""",
                    (item["id"], class_id, student_no, name, item["created_at"]),
                )
        except sqlite3.IntegrityError as error:
            raise ValidationError("student_no already exists in this class") from error
        return item

    def list_assignments(self, class_id):
        with self.database.connection() as connection:
            self._require(connection, "classes", class_id)
            rows = connection.execute(
                "SELECT * FROM assignments WHERE class_id = ? ORDER BY assignment_date DESC, id",
                (class_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def create_assignment(self, class_id, name, assignment_date):
        name = self._required_text(name, "name")
        try:
            assignment_date = date.fromisoformat(assignment_date).isoformat()
        except (TypeError, ValueError) as error:
            raise ValidationError("date must use YYYY-MM-DD") from error
        item = {
            "id": new_id(), "class_id": class_id, "name": name,
            "date": assignment_date, "status": "ACTIVE", "created_at": utc_now(),
        }
        with self.database.connection() as connection:
            self._require(connection, "classes", class_id)
            connection.execute(
                """INSERT INTO assignments
                   (id, class_id, name, assignment_date, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (item["id"], class_id, name, assignment_date, item["status"], item["created_at"]),
            )
        return item

    def list_submissions(self, assignment_id):
        with self.database.connection() as connection:
            self._require(connection, "assignments", assignment_id)
            ids = connection.execute(
                "SELECT id FROM submissions WHERE assignment_id = ? ORDER BY created_at, id",
                (assignment_id,),
            ).fetchall()
        return [self.get_submission(row["id"]) for row in ids]

    def create_submission(self, assignment_id, student_id):
        item = {
            "id": new_id(), "assignment_id": assignment_id, "student_id": student_id,
            "status": "EMPTY", "page_count": 0, "created_at": utc_now(),
            "finished_capture_at": None, "completed_at": None, "error": None,
        }
        try:
            with self.database.connection() as connection:
                assignment = self._require(connection, "assignments", assignment_id)
                student = self._require(connection, "students", student_id)
                if assignment["class_id"] != student["class_id"]:
                    raise ValidationError("student and assignment must belong to the same class")
                connection.execute(
                    """INSERT INTO submissions
                       (id, assignment_id, student_id, status, page_count, created_at)
                       VALUES (?, ?, ?, 'EMPTY', 0, ?)""",
                    (item["id"], assignment_id, student_id, item["created_at"]),
                )
        except sqlite3.IntegrityError as error:
            raise ValidationError("a Submission already exists for this student and Assignment") from error
        return self.get_submission(item["id"])

    def start_submission(self, submission_id):
        with self.database.connection() as connection:
            transition(connection, submission_id, "CAPTURING", utc_now())
        return self.get_submission(submission_id)

    def add_page(self, submission_id, source_ref):
        source_ref = self._required_text(source_ref, "source_ref")
        page_id = new_id()
        with self.database.connection() as connection:
            submission = self._require(connection, "submissions", submission_id)
            if submission["status"] != "CAPTURING":
                raise InvalidTransition(
                    "Pages can only be added while CAPTURING (current: {})".format(submission["status"])
                )
            page_index = submission["page_count"] + 1
            item = {
                "id": page_id, "submission_id": submission_id, "page_index": page_index,
                "source_ref": source_ref, "created_at": utc_now(),
            }
            connection.execute(
                """INSERT INTO submission_pages
                   (id, submission_id, page_index, source_ref, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (page_id, submission_id, page_index, source_ref, item["created_at"]),
            )
            connection.execute(
                "UPDATE submissions SET page_count = ? WHERE id = ?",
                (page_index, submission_id),
            )
        return item

    def add_placeholder_page(self, submission_id):
        submission = self.get_submission(submission_id)
        return self.add_page(
            submission_id,
            "placeholder://submission/{}/page/{}".format(
                submission_id, submission["page_count"] + 1
            ),
        )

    def add_uploaded_page(self, submission_id, filename, content):
        suffix = Path(filename or "").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".heic"}:
            raise ValidationError("image filename must end in jpg, jpeg, png, webp, or heic")
        if not content or len(content) > 10 * 1024 * 1024:
            raise ValidationError("image must be between 1 byte and 10 MB")
        submission = self.get_submission(submission_id)
        if submission["status"] != "CAPTURING":
            raise InvalidTransition("Pages can only be added while CAPTURING")
        disk_name = new_id() + suffix
        destination = self.pages_dir / disk_name
        destination.write_bytes(content)
        source_ref = "pages/" + disk_name
        try:
            page = self.add_page(submission_id, source_ref)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return page

    def finish_submission(self, submission_id):
        with self.database.connection() as connection:
            submission = self._require(connection, "submissions", submission_id)
            if submission["status"] != "CAPTURING":
                raise InvalidTransition(
                    "Submission can only be finished while CAPTURING (current: {})".format(
                        submission["status"]
                    )
                )
            if submission["page_count"] < 1:
                raise ValidationError("Submission requires at least one page before finishing")
            now = utc_now()
            transition(connection, submission_id, "READY", now)
            transition(connection, submission_id, "QUEUED", now)
            connection.execute(
                """INSERT INTO jobs (id, submission_id, status, created_at)
                   VALUES (?, ?, 'QUEUED', ?)""",
                (new_id(), submission_id, now),
            )
        return self.get_submission(submission_id)

    def get_submission(self, submission_id):
        with self.database.connection() as connection:
            row = self._require(connection, "submissions", submission_id)
            pages = connection.execute(
                "SELECT * FROM submission_pages WHERE submission_id = ? ORDER BY page_index",
                (submission_id,),
            ).fetchall()
            results = connection.execute(
                """SELECT * FROM recognition_results
                   WHERE submission_id = ? ORDER BY created_at, id""",
                (submission_id,),
            ).fetchall()
            job = connection.execute(
                "SELECT id, status, error FROM jobs WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
        result = self._row(row)
        result["pages"] = [self._row(page) for page in pages]
        result["results"] = [self._result_row(item) for item in results]
        result["job"] = self._row(job) if job else None
        return result

    def process_next_job(self):
        with self.database.connection() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE status = 'QUEUED' ORDER BY sequence LIMIT 1"
            ).fetchone()
            if job is None:
                return False
            transition(connection, job["submission_id"], "PROCESSING", utc_now())
            connection.execute(
                "UPDATE jobs SET status = 'RUNNING', started_at = ?, error = NULL WHERE id = ?",
                (utc_now(), job["id"]),
            )

        try:
            self._process_submission(job["submission_id"])
            with self.database.connection() as connection:
                transition(connection, job["submission_id"], "COMPLETED", utc_now())
                connection.execute(
                    "UPDATE jobs SET status = 'COMPLETED', completed_at = ? WHERE id = ?",
                    (utc_now(), job["id"]),
                )
        except Exception as error:
            message = "{}: {}".format(type(error).__name__, error)
            with self.database.connection() as connection:
                transition(connection, job["submission_id"], "FAILED", utc_now(), error=message)
                connection.execute(
                    "UPDATE jobs SET status = 'FAILED', error = ?, completed_at = ? WHERE id = ?",
                    (message, utc_now(), job["id"]),
                )
        return True

    def recover_interrupted_jobs(self):
        with self.database.connection() as connection:
            jobs = connection.execute("SELECT id, submission_id FROM jobs WHERE status = 'RUNNING'").fetchall()
            now = utc_now()
            for job in jobs:
                transition(connection, job["submission_id"], "QUEUED", now)
                connection.execute(
                    "UPDATE jobs SET status = 'QUEUED', started_at = NULL WHERE id = ?",
                    (job["id"],),
                )

    def _process_submission(self, submission_id):
        submission = self.get_submission(submission_id)
        for page in submission["pages"]:
            result = self.gateway.recognize(
                source_ref=page["source_ref"],
                answer_type="integer",
                context={"submission_id": submission_id, "page_index": page["page_index"]},
            )
            payload = result.to_dict()
            with self.database.connection() as connection:
                connection.execute(
                    """INSERT OR REPLACE INTO recognition_results
                       (id, submission_id, page_id, text, normalized_candidate, confidence,
                        provider, model, latency_ms, metadata_json, error, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        new_id(), submission_id, page["id"], payload["text"],
                        payload["normalized_candidate"], payload["confidence"],
                        payload["provider"], payload["model"], payload["latency_ms"],
                        json.dumps(payload["metadata"], ensure_ascii=False), payload["error"], utc_now(),
                    ),
                )
            if result.error:
                raise ProcessingError(result.error)

    def job_counts(self):
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
        return {row["status"]: row["count"] for row in rows}

    @staticmethod
    def decode_image_payload(body):
        filename = body.get("filename")
        encoded = body.get("image_base64")
        if not isinstance(encoded, str):
            raise ValidationError("image_base64 is required")
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as error:
            raise ValidationError("image_base64 is invalid") from error
        return filename, content

    @staticmethod
    def _required_text(value, field):
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("{} is required".format(field))
        return value.strip()

    @staticmethod
    def _require(connection, table, item_id):
        allowed = {"classes", "students", "assignments", "submissions"}
        if table not in allowed:
            raise ValueError("Unsupported table")
        row = connection.execute("SELECT * FROM {} WHERE id = ?".format(table), (item_id,)).fetchone()
        if row is None:
            raise NotFound("{} not found: {}".format(table[:-1].capitalize(), item_id))
        return row

    @staticmethod
    def _row(row):
        if row is None:
            return None
        result = dict(row)
        if "active" in result:
            result["active"] = bool(result["active"])
        if "assignment_date" in result:
            result["date"] = result.pop("assignment_date")
        return result

    @classmethod
    def _result_row(cls, row):
        result = cls._row(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        return result
