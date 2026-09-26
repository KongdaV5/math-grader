import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import uuid

from local_service.database import Database
from local_service.recognition import RecognitionGateway
from local_service.runtime_paths import RuntimePaths
from local_service.model_catalog import ModelCatalog
from local_service.model_manager import ModelManager
from local_service.templates import TemplateService
from local_service.image_pipeline import ImagePipeline
from local_service.state_machine import InvalidTransition, transition


class NotFound(LookupError):
    pass


class ValidationError(ValueError):
    pass


class ProcessingError(RuntimeError):
    pass


class Unauthorized(Exception):
    pass


class PayloadTooLarge(ValidationError):
    pass


class UnsupportedMediaType(ValidationError):
    pass


MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/avif": ".avif",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id():
    return str(uuid.uuid4())


class MathGraderService:
    def __init__(self, database_path, data_dir=None, recognition_config=None, registry=None):
        self.database = Database(database_path)
        self.data_dir = Path(data_dir) if data_dir else Path(database_path).parent
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths = RuntimePaths(self.data_dir).ensure()
        self.pages_dir = (self.paths.originals if Path(database_path).parent == self.paths.data
                          else self.paths.legacy_pages)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.model_catalog = ModelCatalog()
        self.model_manager = ModelManager(self.model_catalog, self.paths)
        self.gateway = RecognitionGateway.from_file(recognition_config, registry=registry,
                                                     catalog=self.model_catalog, manager=self.model_manager)
        self.templates = TemplateService(self.database)
        self.image_pipeline = ImagePipeline(self.paths.processed)
        self.recover_interrupted_jobs()
        self.expire_orphaned_capture_sessions()

    def health(self):
        with self.database.connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "service": "math-grader-local", "runtime_version": sys.version.split()[0],
                "python_supported": sys.version_info >= (3, 9)}

    def system_info(self):
        return {"paths": self.paths.describe(), "runtime_version": sys.version.split()[0],
                "python_supported": sys.version_info >= (3, 9),
                "recognition_config": {"schema_version": self.gateway.config.get("schema_version", 1),
                                       "routes": list(self.gateway.config.get("recognition", {})),
                                       "model_routes": self.gateway.config.get("model_routes", {})}}

    def open_directory(self, key):
        allowed = {"root", "data", "originals", "processed", "models", "cache", "logs", "config"}
        if key not in allowed:
            raise ValidationError("Unknown directory")
        path = getattr(self.paths, key)
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(path)

    def overview(self):
        with self.database.connection() as connection:
            counts = {
                "classes": connection.execute("SELECT COUNT(*) FROM classes").fetchone()[0],
                "students": connection.execute("SELECT COUNT(*) FROM students").fetchone()[0],
                "queued": connection.execute("SELECT COUNT(*) FROM submissions WHERE status='QUEUED'").fetchone()[0],
                "processing": connection.execute("SELECT COUNT(*) FROM submissions WHERE status='PROCESSING'").fetchone()[0],
            }
            assignments = [self._row(row) for row in connection.execute(
                "SELECT * FROM assignments ORDER BY created_at DESC,id DESC LIMIT 5")]
            submissions = [self._row(row) for row in connection.execute(
                "SELECT * FROM submissions ORDER BY created_at DESC,id DESC LIMIT 5")]
        return {"counts": counts, "recent_assignments": assignments, "recent_submissions": submissions}

    def process_page_image(self, page_id):
        with self.database.connection() as connection:
            row = self._require(connection, "submission_pages", page_id)
        path = self._stored_page_path(row["source_ref"])
        if path is None or not path.is_file():
            raise NotFound("Stored page image not found")
        return self.image_pipeline.process(path).to_dict()

    def import_template_reference(self, page_id, payload):
        self.templates.get_page_template(page_id)
        filename, content = self.decode_image_payload(payload)
        mime_type = self._validated_image_mime(content, None)
        if len(content) > MAX_IMAGE_BYTES:
            raise PayloadTooLarge("Image exceeds 10 MB")
        destination = self.paths.originals / (new_id() + IMAGE_EXTENSIONS[mime_type])
        temporary = destination.with_name("." + destination.name + ".upload")
        try:
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
            return self.templates.set_reference_image(page_id, str(destination.relative_to(self.data_dir)))
        finally:
            temporary.unlink(missing_ok=True)

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
        mime_type = self._validated_image_mime(content, None)
        page, _ = self._persist_uploaded_page(submission_id, filename, mime_type, content)
        return page

    def add_capture_uploaded_page(
        self, token, filename, mime_type, content, client_upload_id, expected_submission_id
    ):
        mime_type = self._validated_image_mime(content, mime_type)
        try:
            parsed_upload_id = str(uuid.UUID(client_upload_id))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValidationError("Idempotency-Key must be a UUID") from error
        if parsed_upload_id != client_upload_id:
            raise ValidationError("Idempotency-Key must be a canonical UUID")
        session = self.authorized_capture_session(token)
        if session["current_submission_id"] is None:
            raise InvalidTransition("This Capture Session has no remaining students")
        if session["current_submission_id"] != expected_submission_id:
            raise InvalidTransition("Upload does not belong to the current student")
        page, duplicate = self._persist_uploaded_page(
            session["current_submission_id"], filename, mime_type, content,
            client_upload_id=client_upload_id, token=token,
            expected_submission_id=expected_submission_id,
        )
        return {"page": page, "idempotent": duplicate}

    def _persist_uploaded_page(self, submission_id, filename, mime_type, content,
                               client_upload_id=None, token=None, expected_submission_id=None):
        if not isinstance(content, bytes) or not content:
            raise ValidationError("Image must not be empty")
        if len(content) > MAX_IMAGE_BYTES:
            raise PayloadTooLarge("Image exceeds 10 MB")
        safe_filename = self._safe_original_filename(filename)
        digest = hashlib.sha256(content).hexdigest()
        page_id = new_id()
        extension = IMAGE_EXTENSIONS[mime_type]
        disk_name = page_id + extension
        temporary = self.pages_dir / ("." + page_id + ".upload")
        destination = self.pages_dir / disk_name
        created_path = False
        item = None
        idempotent = False
        try:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if token is not None:
                    session = self._require_capture_session(connection, token)
                    if (session["current_submission_id"] != submission_id or
                            (expected_submission_id is not None and
                             expected_submission_id != session["current_submission_id"])):
                        raise InvalidTransition("Upload does not belong to the current student")
                submission = self._require(connection, "submissions", submission_id)
                if submission["status"] != "CAPTURING":
                    raise InvalidTransition("Pages can only be added while CAPTURING")

                if client_upload_id is not None:
                    existing = connection.execute(
                        "SELECT * FROM submission_pages WHERE client_upload_id = ?",
                        (client_upload_id,),
                    ).fetchone()
                    if existing is not None:
                        if (existing["submission_id"] != submission_id or
                                existing["content_sha256"] != digest):
                            raise ValidationError("Idempotency-Key was already used for another upload")
                        item = self._row(existing)
                        idempotent = True
                    else:
                        item = None
                else:
                    item = None

                if item is None:
                    page_index = connection.execute(
                        "SELECT COALESCE(MAX(page_index), 0) FROM submission_pages WHERE submission_id = ?",
                        (submission_id,),
                    ).fetchone()[0] + 1
                    uploaded_at = utc_now()
                    with temporary.open("xb") as image_file:
                        image_file.write(content)
                        image_file.flush()
                        os.fsync(image_file.fileno())
                    os.replace(str(temporary), str(destination))
                    created_path = True
                    item = {
                        "id": page_id,
                        "submission_id": submission_id,
                        "page_index": page_index,
                        "source_ref": str(self.pages_dir.relative_to(self.data_dir) / disk_name),
                        "created_at": uploaded_at,
                        "original_filename": safe_filename,
                        "mime_type": mime_type,
                        "byte_size": len(content),
                        "uploaded_at": uploaded_at,
                        "content_sha256": digest,
                        "client_upload_id": client_upload_id,
                    }
                    connection.execute(
                        """INSERT INTO submission_pages
                           (id, submission_id, page_index, source_ref, created_at,
                            original_filename, mime_type, byte_size, uploaded_at,
                            content_sha256, client_upload_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            item["id"], item["submission_id"], item["page_index"],
                            item["source_ref"], item["created_at"], item["original_filename"],
                            item["mime_type"], item["byte_size"], item["uploaded_at"],
                            item["content_sha256"], item["client_upload_id"],
                        ),
                    )
                    connection.execute(
                        "UPDATE submissions SET page_count = ? WHERE id = ?",
                        (page_index, submission_id),
                    )
        except Exception:
            temporary.unlink(missing_ok=True)
            if created_path:
                destination.unlink(missing_ok=True)
            raise
        return item, idempotent

    @classmethod
    def _validated_image_mime(cls, content, declared_mime):
        if not isinstance(content, bytes) or not content:
            raise ValidationError("Image must not be empty")
        if len(content) > MAX_IMAGE_BYTES:
            raise PayloadTooLarge("Image exceeds 10 MB")
        actual = cls._sniff_image_mime(content)
        if actual is None:
            raise UnsupportedMediaType("Only JPEG, PNG, WebP, HEIC, HEIF, or AVIF images are accepted")
        if declared_mime is None or not str(declared_mime).strip():
            return actual
        declared = str(declared_mime).split(";", 1)[0].strip().lower()
        if declared not in IMAGE_EXTENSIONS:
            raise UnsupportedMediaType("Unsupported image MIME type")
        compatible = declared == actual or {declared, actual} <= {"image/heic", "image/heif"}
        if not compatible:
            raise UnsupportedMediaType("MIME type does not match the uploaded image")
        return actual

    @staticmethod
    def _sniff_image_mime(content):
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return "image/webp"
        if len(content) >= 12 and content[4:8] == b"ftyp":
            brand = content[8:12].lower()
            if brand in {b"heic", b"heix", b"hevc", b"hevx"}:
                return "image/heic"
            if brand in {b"mif1", b"msf1"}:
                return "image/heif"
            if brand in {b"avif", b"avis"}:
                return "image/avif"
        return None

    @staticmethod
    def _safe_original_filename(filename):
        if not isinstance(filename, str):
            return None
        leaf = filename.replace("\\", "/").split("/")[-1]
        leaf = "".join(character for character in leaf if ord(character) >= 32 and ord(character) != 127)
        leaf = leaf.strip()[:255]
        return leaf or None

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

    def expire_orphaned_capture_sessions(self):
        """A process restart loses the in-memory token and LAN listener, so old sessions expire."""
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """UPDATE capture_sessions SET status = 'EXPIRED', ended_at = ?
                   WHERE status = 'ACTIVE'""",
                (now,),
            )

    def expire_stale_capture_sessions(self):
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """UPDATE capture_sessions SET status = 'EXPIRED', ended_at = ?
                   WHERE status = 'ACTIVE' AND expires_at <= ?""",
                (now, now),
            )

    def start_capture_session(self, assignment_id, expires_in_seconds=8 * 60 * 60):
        if not isinstance(expires_in_seconds, int) or not 1 <= expires_in_seconds <= 24 * 60 * 60:
            raise ValidationError("Capture Session lifetime must be between 1 second and 24 hours")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        session_id = new_id()
        now = utc_now()
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)).isoformat(
            timespec="seconds"
        )
        try:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """UPDATE capture_sessions SET status = 'EXPIRED', ended_at = ?
                       WHERE status = 'ACTIVE' AND expires_at <= ?""",
                    (now, now),
                )
                active = connection.execute(
                    "SELECT id FROM capture_sessions WHERE status = 'ACTIVE' LIMIT 1"
                ).fetchone()
                if active is not None:
                    raise ValidationError("A Capture Session is already active")
                assignment = self._require(connection, "assignments", assignment_id)
                if assignment["status"] != "ACTIVE":
                    raise ValidationError("Assignment is closed")
                selected = self._next_capture_submission_locked(connection, assignment_id, now)
                if selected is None:
                    raise ValidationError("No active students remain to capture for this Assignment")
                student, submission = selected
                connection.execute(
                    """INSERT INTO capture_sessions
                       (id, assignment_id, token_hash, created_at, expires_at, status,
                        current_student_id, current_submission_id)
                       VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)""",
                    (
                        session_id, assignment_id, token_hash, now, expires_at,
                        student["id"], submission["id"],
                    ),
                )
                connection.execute(
                    """INSERT INTO capture_session_submissions
                       (session_id, submission_id, student_id, started_at)
                       VALUES (?, ?, ?, ?)""",
                    (session_id, submission["id"], student["id"], now),
                )
        except sqlite3.IntegrityError as error:
            raise ValidationError("A Capture Session is already active") from error
        return {
            "session_id": session_id,
            "assignment_id": assignment_id,
            "token": token,
            "created_at": now,
            "expires_at": expires_at,
            "current_student_id": student["id"],
            "current_submission_id": submission["id"],
        }

    def end_capture_session(self, session_id=None):
        now = utc_now()
        with self.database.connection() as connection:
            if session_id is None:
                row = connection.execute(
                    "SELECT id FROM capture_sessions WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    return None
                session_id = row["id"]
            connection.execute(
                """UPDATE capture_sessions SET status = 'ENDED', ended_at = ?
                   WHERE id = ? AND status = 'ACTIVE'""",
                (now, session_id),
            )
            row = connection.execute("SELECT * FROM capture_sessions WHERE id = ?", (session_id,)).fetchone()
        return self._row(row) if row else None

    def authorized_capture_session(self, token):
        with self.database.connection() as connection:
            return self._require_capture_session(connection, token)

    def validate_capture_upload_target(self, token, submission_id):
        with self.database.connection() as connection:
            session = self._require_capture_session(connection, token)
            if not submission_id or session["current_submission_id"] != submission_id:
                raise InvalidTransition("Upload does not belong to the current student")

    def capture_session_is_active(self, session_id):
        self.expire_stale_capture_sessions()
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT status FROM capture_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return bool(row and row["status"] == "ACTIVE")

    def capture_admin_state(self):
        self.expire_stale_capture_sessions()
        with self.database.connection() as connection:
            session = connection.execute(
                "SELECT * FROM capture_sessions ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if session is None:
                return {"status": "INACTIVE", "session": None}
            if session["status"] != "ACTIVE":
                return {"status": session["status"], "session": self._capture_session_summary(session)}
            return {
                "status": "ACTIVE",
                "session": self._capture_session_summary(session),
                "capture": self._capture_state_locked(connection, session),
            }

    def current_capture(self, token):
        with self.database.connection() as connection:
            session = self._require_capture_session(connection, token)
            return self._capture_state_locked(connection, session)

    def finish_capture_submission(self, token, submission_id):
        now = utc_now()
        already_finished = False
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            session = self._require_capture_session(connection, token)
            mapping = connection.execute(
                """SELECT * FROM capture_session_submissions
                   WHERE session_id = ? AND submission_id = ?""",
                (session["id"], submission_id),
            ).fetchone()
            if mapping is None:
                raise NotFound("Submission is not part of this Capture Session")
            if mapping["finished_at"] is not None:
                already_finished = True
            else:
                if session["current_submission_id"] != submission_id:
                    raise InvalidTransition("Only the current student's Submission can be finished")
                submission = self._require(connection, "submissions", submission_id)
                if submission["status"] != "CAPTURING":
                    raise InvalidTransition("Submission is no longer CAPTURING")
                if submission["page_count"] < 1:
                    raise ValidationError("Submission requires at least one page before finishing")
                transition(connection, submission_id, "READY", now)
                transition(connection, submission_id, "QUEUED", now)
                connection.execute(
                    """INSERT INTO jobs (id, submission_id, status, created_at)
                       VALUES (?, ?, 'QUEUED', ?)""",
                    (new_id(), submission_id, now),
                )
                connection.execute(
                    """UPDATE capture_session_submissions SET finished_at = ?
                       WHERE session_id = ? AND submission_id = ?""",
                    (now, session["id"], submission_id),
                )
                selected = self._next_capture_submission_locked(
                    connection, session["assignment_id"], now
                )
                if selected is None:
                    connection.execute(
                        """UPDATE capture_sessions SET current_student_id = NULL,
                           current_submission_id = NULL WHERE id = ?""",
                        (session["id"],),
                    )
                else:
                    student, next_submission = selected
                    connection.execute(
                        """INSERT INTO capture_session_submissions
                           (session_id, submission_id, student_id, started_at)
                           VALUES (?, ?, ?, ?)""",
                        (session["id"], next_submission["id"], student["id"], now),
                    )
                    connection.execute(
                        """UPDATE capture_sessions SET current_student_id = ?,
                           current_submission_id = ? WHERE id = ?""",
                        (student["id"], next_submission["id"], session["id"]),
                    )
        return {
            "submission": self.get_submission(submission_id),
            "current": self.current_capture(token),
            "already_finished": already_finished,
        }

    def delete_capture_page(self, token, page_id):
        source_path = None
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            session = self._require_capture_session(connection, token)
            if session["current_submission_id"] is None:
                raise InvalidTransition("This Capture Session has no current student")
            page = connection.execute(
                "SELECT * FROM submission_pages WHERE id = ? AND submission_id = ?",
                (page_id, session["current_submission_id"]),
            ).fetchone()
            if page is None:
                raise NotFound("Page not found for the current student")
            source_path = self._stored_page_path(page["source_ref"])
            connection.execute("DELETE FROM submission_pages WHERE id = ?", (page_id,))
            connection.execute(
                """UPDATE submission_pages SET page_index = page_index + 1000000
                   WHERE submission_id = ? AND page_index > ?""",
                (session["current_submission_id"], page["page_index"]),
            )
            connection.execute(
                """UPDATE submission_pages SET page_index = page_index - 1000001
                   WHERE submission_id = ? AND page_index > 1000000""",
                (session["current_submission_id"],),
            )
            remaining = connection.execute(
                "SELECT COUNT(*) FROM submission_pages WHERE submission_id = ?",
                (session["current_submission_id"],),
            ).fetchone()[0]
            connection.execute(
                "UPDATE submissions SET page_count = ? WHERE id = ?",
                (remaining, session["current_submission_id"]),
            )
        if source_path is not None:
            source_path.unlink(missing_ok=True)
        return self.current_capture(token)

    def capture_page_image(self, token, page_id):
        with self.database.connection() as connection:
            session = self._require_capture_session(connection, token)
            if session["current_submission_id"] is None:
                raise NotFound("Page not found for the current student")
            page = connection.execute(
                "SELECT * FROM submission_pages WHERE id = ? AND submission_id = ?",
                (page_id, session["current_submission_id"]),
            ).fetchone()
            if page is None or not page["mime_type"]:
                raise NotFound("Page image not found for the current student")
            image_path = self._stored_page_path(page["source_ref"])
            if image_path is None:
                raise NotFound("Page image not found for the current student")
            mime_type = page["mime_type"]
        try:
            return image_path.read_bytes(), mime_type
        except FileNotFoundError as error:
            raise NotFound("Page image file is missing") from error

    def _require_capture_session(self, connection, token):
        session = connection.execute(
            "SELECT * FROM capture_sessions WHERE status = 'ACTIVE' LIMIT 1"
        ).fetchone()
        if session is None:
            raise Unauthorized("Capture Session token is invalid or no longer active")
        presented = token.encode("utf-8") if isinstance(token, str) and len(token) <= 256 else b""
        token_hash = hashlib.sha256(presented).hexdigest()
        if not hmac.compare_digest(session["token_hash"], token_hash):
            raise Unauthorized("Capture Session token is invalid or no longer active")
        if datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc):
            raise Unauthorized("Capture Session token is invalid or no longer active")
        return session

    def _next_capture_submission_locked(self, connection, assignment_id, now):
        assignment = self._require(connection, "assignments", assignment_id)
        students = connection.execute(
            """SELECT students.* FROM students
               JOIN classes ON classes.id = students.class_id
               WHERE students.class_id = ? AND students.active = 1 AND classes.active = 1
               ORDER BY students.student_no COLLATE NOCASE, students.id""",
            (assignment["class_id"],),
        ).fetchall()
        for student in students:
            submission = connection.execute(
                "SELECT * FROM submissions WHERE assignment_id = ? AND student_id = ?",
                (assignment_id, student["id"]),
            ).fetchone()
            if submission is None:
                submission_id = new_id()
                connection.execute(
                    """INSERT INTO submissions
                       (id, assignment_id, student_id, status, page_count, created_at)
                       VALUES (?, ?, ?, 'EMPTY', 0, ?)""",
                    (submission_id, assignment_id, student["id"], now),
                )
                submission = self._require(connection, "submissions", submission_id)
            if submission["status"] == "EMPTY":
                transition(connection, submission["id"], "CAPTURING", now)
                submission = self._require(connection, "submissions", submission["id"])
            if submission["status"] == "CAPTURING":
                return student, submission
        return None

    def _capture_state_locked(self, connection, session):
        assignment = self._require(connection, "assignments", session["assignment_id"])
        classroom = self._require(connection, "classes", assignment["class_id"])
        current = None
        if session["current_submission_id"] is not None:
            student = self._require(connection, "students", session["current_student_id"])
            submission = self._require(connection, "submissions", session["current_submission_id"])
            pages = connection.execute(
                """SELECT id, page_index, original_filename, mime_type, byte_size, uploaded_at
                   FROM submission_pages WHERE submission_id = ? ORDER BY page_index""",
                (submission["id"],),
            ).fetchall()
            current = {
                "submission_id": submission["id"],
                "student_id": student["id"],
                "student_name": student["name"],
                "student_no": student["student_no"],
                "status": submission["status"],
                "page_count": submission["page_count"],
                "pages": [self._row(page) for page in pages],
            }
        totals = connection.execute(
            """SELECT COUNT(*) FROM students JOIN classes ON classes.id = students.class_id
               WHERE students.class_id = ? AND students.active = 1 AND classes.active = 1""",
            (assignment["class_id"],),
        ).fetchone()[0]
        finished = connection.execute(
            """SELECT COUNT(*) FROM capture_session_submissions
               WHERE session_id = ? AND finished_at IS NOT NULL""",
            (session["id"],),
        ).fetchone()[0]
        last_finished = connection.execute(
            """SELECT students.name, submissions.status, capture_session_submissions.finished_at
               FROM capture_session_submissions
               JOIN students ON students.id = capture_session_submissions.student_id
               JOIN submissions ON submissions.id = capture_session_submissions.submission_id
               WHERE capture_session_submissions.session_id = ?
                 AND capture_session_submissions.finished_at IS NOT NULL
               ORDER BY capture_session_submissions.finished_at DESC LIMIT 1""",
            (session["id"],),
        ).fetchone()
        processing = connection.execute(
            """SELECT students.name AS student_name, submissions.status,
                      submissions.page_count, jobs.status AS job_status
               FROM submissions JOIN students ON students.id = submissions.student_id
               LEFT JOIN jobs ON jobs.submission_id = submissions.id
               WHERE submissions.assignment_id = ?
                 AND (submissions.status IN ('QUEUED', 'PROCESSING')
                      OR jobs.status IN ('QUEUED', 'RUNNING'))
               ORDER BY submissions.created_at, submissions.id""",
            (assignment["id"],),
        ).fetchall()
        return {
            "session_id": session["id"],
            "status": session["status"],
            "created_at": session["created_at"],
            "expires_at": session["expires_at"],
            "class_name": classroom["name"],
            "assignment_name": assignment["name"],
            "current": current,
            "complete": current is None,
            "finished_count": finished,
            "total_students": totals,
            "last_finished": self._row(last_finished),
            "processing": [self._row(row) for row in processing],
        }

    @staticmethod
    def _capture_session_summary(session):
        fields = (
            "id", "assignment_id", "created_at", "expires_at", "ended_at", "status",
            "current_student_id", "current_submission_id",
        )
        return {field: session[field] for field in fields}

    def _stored_page_path(self, source_ref):
        if not isinstance(source_ref, str) or not (
            source_ref.startswith("pages/") or source_ref.startswith("images/originals/")
        ):
            return None
        pages_root = (self.paths.legacy_pages if source_ref.startswith("pages/")
                      else self.paths.originals).resolve()
        image_path = (self.data_dir / source_ref).resolve()
        try:
            image_path.relative_to(pages_root)
        except ValueError as error:
            raise ValidationError("Stored page path is outside the image directory") from error
        return image_path

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
        allowed = {"classes", "students", "assignments", "submissions", "submission_pages"}
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
