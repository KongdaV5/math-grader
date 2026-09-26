from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import logging
from pathlib import Path
import socket
from urllib.parse import parse_qs, unquote, urlsplit

from local_service.service import (
    MathGraderService,
    NotFound,
    PayloadTooLarge,
    Unauthorized,
    UnsupportedMediaType,
    ValidationError,
)
from local_service.state_machine import InvalidTransition
from local_service.errors import DomainError


logger = logging.getLogger(__name__)
ALLOWED_ORIGINS = {
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
}
MAX_REQUEST_BYTES = 15 * 1024 * 1024


class ServiceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service, capture_bridge):
        self.service = service
        self.capture_bridge = capture_bridge
        super().__init__(address, ServiceRequestHandler)


class ServiceRequestHandler(BaseHTTPRequestHandler):
    server_version = "MathGraderLocal/0.1"

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        try:
            segments = self._segments()
            if segments == ["health"]:
                return self._send_json(200, self.server.service.health())
            if len(segments)==4 and segments[:2]==["api","images"]:
                return self._send_image(*self.server.service.slice.image_bytes(segments[2],segments[3]))
            if segments == ["api", "review", "queue"]:
                return self._send_json(200, self.server.service.teacher_workflow.review_queue())
            if len(segments) == 4 and segments[:2] == ["api", "assignments"] and segments[3] == "exam-template":
                return self._send_json(200, self.server.service.teacher_workflow.get_exam_template(segments[2]))
            if len(segments) == 4 and segments[:2] == ["api", "submissions"] and segments[3] == "grade":
                return self._send_json(200, self.server.service.teacher_workflow.grade_result(segments[2]))
            if len(segments)==4 and segments[:2]==["api","pages"]:
                if segments[3]=="detail":
                    return self._send_json(200,self.server.service.slice.page_detail(segments[2]))
                if segments[3]=="match":
                    return self._send_json(200,self.server.service.slice.match_templates(segments[2]))
                if segments[3]=="predictions":
                    return self._send_json(200,self.server.service.slice.export_predictions(segments[2]))
            if segments == ["api", "overview"]:
                return self._send_json(200, self.server.service.overview())
            if segments == ["api", "system"]:
                return self._send_json(200, self.server.service.system_info())
            if segments == ["api", "models"]:
                return self._send_json(200, self.server.service.model_manager.list_models())
            if len(segments) == 3 and segments[:2] == ["api", "models"]:
                return self._send_json(200, self.server.service.model_manager.get_model_status(segments[2]))
            if len(segments) == 4 and segments[:2] == ["api", "models"]:
                model_id, resource = segments[2], segments[3]
                if resource == "health":
                    return self._send_json(200, self.server.service.gateway.model_registry.health(model_id))
                if resource == "manifest":
                    return self._send_json(200, self.server.service.model_manager.verify_model(model_id))
            if segments == ["api", "templates", "groups"]:
                return self._send_json(200, self.server.service.templates.list_template_groups())
            if len(segments) == 5 and segments[:3] == ["api", "templates", "groups"] and segments[4] == "pages":
                return self._send_json(200, self.server.service.templates.list_page_templates(segments[3]))
            if len(segments) == 4 and segments[:3] == ["api", "templates", "pages"]:
                return self._send_json(200, self.server.service.templates.get_page_template(segments[3]))
            if len(segments) == 5 and segments[:3] == ["api", "templates", "pages"] and segments[4] == "questions":
                return self._send_json(200, self.server.service.templates.list_questions(segments[3]))
            if len(segments) == 5 and segments[:3] == ["api", "templates", "questions"] and segments[4] == "regions":
                return self._send_json(200, self.server.service.templates.list_answer_regions(segments[3]))
            if segments == ["api", "classes"]:
                return self._send_json(200, self.server.service.list_classes())
            if len(segments) == 4 and segments[:2] == ["api", "classes"]:
                class_id, resource = segments[2], segments[3]
                if resource == "students":
                    return self._send_json(200, self.server.service.list_students(class_id))
                if resource == "assignments":
                    return self._send_json(200, self.server.service.list_assignments(class_id))
            if len(segments) == 4 and segments[:2] == ["api", "assignments"] and segments[3] == "submissions":
                return self._send_json(200, self.server.service.list_submissions(segments[2]))
            if len(segments) == 3 and segments[:2] == ["api", "submissions"]:
                return self._send_json(200, self.server.service.get_submission(segments[2]))
            if segments == ["api", "jobs"]:
                return self._send_json(200, self.server.service.job_counts())
            if segments == ["api", "capture", "session"]:
                return self._send_json(200, self.server.capture_bridge.snapshot())
            return self._send_json(404, {"error": "Route not found"})
        except Exception as error:
            return self._handle_error(error)

    def do_POST(self):
        try:
            segments = self._segments()
            body = self._read_json()
            service = self.server.service
            if len(segments) == 4 and segments[:2] == ["api", "models"]:
                model_id, action = segments[2], segments[3]
                manager = service.model_manager
                if action == "install":
                    return self._send_json(202, manager.install_model(model_id))
                if action == "retry":
                    return self._send_json(202, manager.retry_install(model_id))
                if action == "cancel":
                    return self._send_json(200, manager.cancel_install(model_id))
                if action == "remove":
                    service.gateway.model_registry.unload(model_id)
                    return self._send_json(200, manager.remove_model(model_id, service.gateway.model_registry.can_remove))
                if action == "verify":
                    return self._send_json(200, manager.verify_model(model_id))
                if action == "open":
                    return self._send_json(200, {"path": manager.open_model_directory(model_id)})
                if action == "health":
                    return self._send_json(200, service.gateway.model_registry.health(model_id, load=bool(body.get("load"))))
            if len(segments) == 4 and segments[:2] == ["api", "system"] and segments[2] == "open":
                return self._send_json(200, {"path": service.open_directory(segments[3])})
            if segments == ["api", "templates", "groups"]:
                return self._send_json(201, service.templates.create_template_group(
                    body.get("name"), body.get("grade"), body.get("semester"), body.get("book_name"), body.get("publisher")))
            if len(segments) == 5 and segments[:3] == ["api", "templates", "groups"] and segments[4] == "pages":
                return self._send_json(201, service.templates.create_page_template(
                    segments[3], body.get("page_number"), body.get("name")))
            if len(segments) == 5 and segments[:3] == ["api", "templates", "pages"]:
                page_id, action = segments[3], segments[4]
                if action == "reference":
                    return self._send_json(200, service.import_template_reference(page_id, body))
                if action == "questions":
                    return self._send_json(201, service.templates.create_question(
                        page_id, body.get("question_no"), body.get("answer_type"), body.get("correct_answer"),
                        body.get("accepted_answers"), body.get("score", 1), body.get("knowledge_tag"), body.get("metadata")))
            if len(segments) == 5 and segments[:3] == ["api", "templates", "questions"] and segments[4] == "regions":
                return self._send_json(201, service.templates.create_answer_region(
                    segments[3], body.get("region_index"), body.get("x"), body.get("y"),
                    body.get("width"), body.get("height"), body.get("metadata")))
            if segments == ["api", "lab", "import"]:
                filename,content=service.decode_image_payload(body)
                return self._send_json(201,service.slice.import_lab_image(filename,content))
            if len(segments)==4 and segments[:2]==["api","crops"] and segments[3]=="runs":
                return self._send_json(202,service.slice.queue_recognition(segments[2],body.get("model_id")))
            if len(segments)==4 and segments[:2]==["api","pages"] and segments[3]=="bind":
                return self._send_json(200,service.slice.bind_template(segments[2],body.get("template_id")))
            if len(segments)==4 and segments[:2]==["api","pages"] and segments[3]=="crops":
                return self._send_json(201,service.slice.create_crops(segments[2]))
            if len(segments) == 4 and segments[:2] == ["api", "pages"] and segments[3] == "process":
                return self._send_json(200, service.process_page_image(segments[2]))
            if segments == ["api", "capture", "session", "start"]:
                return self._send_json(
                    201,
                    self.server.capture_bridge.start(body.get("assignment_id"), body.get("host")),
                )
            if segments == ["api", "capture", "session", "end"]:
                return self._send_json(200, self.server.capture_bridge.end())
            if segments == ["api", "classes"]:
                return self._send_json(201, service.create_class(body.get("name")))
            if len(segments) == 4 and segments[:2] == ["api", "classes"]:
                class_id, resource = segments[2], segments[3]
                if resource == "students":
                    return self._send_json(
                        201, service.create_student(class_id, body.get("student_no"), body.get("name"))
                    )
                if resource == "assignments":
                    return self._send_json(
                        201,
                        service.create_assignment(class_id, body.get("name"), body.get("date"),
                                                  body.get("workflow_mode", "LEGACY")),
                    )
            if segments == ["api", "submissions"]:
                return self._send_json(
                    201, service.create_submission(body.get("assignment_id"), body.get("student_id"))
                )
            if len(segments) == 4 and segments[:2] == ["api", "submissions"]:
                submission_id, action = segments[2], segments[3]
                if action == "start":
                    return self._send_json(200, service.start_submission(submission_id))
                if action == "pages":
                    if body.get("placeholder") is True:
                        page = service.add_placeholder_page(submission_id)
                    else:
                        filename, content = service.decode_image_payload(body)
                        page = service.add_uploaded_page(submission_id, filename, content)
                    return self._send_json(201, {"page": page, "submission": service.get_submission(submission_id)})
                if action == "finish":
                    return self._send_json(202, service.finish_submission(submission_id))
                if action == "grade":
                    return self._send_json(202, service.teacher_workflow.enqueue_grading(submission_id))
            if len(segments) == 4 and segments[:2] == ["api", "assignments"] and segments[3] == "teacher-workflow":
                return self._send_json(200, service.teacher_workflow.enable_assignment(segments[2]))
            if len(segments) == 5 and segments[:2] == ["api", "assignments"] and segments[3] == "exam-template":
                assignment_id, action = segments[2], segments[4]
                if action == "analyze":
                    return self._send_json(200, service.teacher_workflow.analyze_exam(
                        assignment_id, body.get("submission_id")))
                if action == "library":
                    return self._send_json(200, service.teacher_workflow.choose_library_template(
                        assignment_id, body.get("template_group_id")))
                if action == "confirm":
                    return self._send_json(200, service.teacher_workflow.confirm_exam(assignment_id))
            if len(segments) == 4 and segments[:2] == ["api", "question-results"] and segments[3] == "review":
                return self._send_json(200, service.teacher_workflow.review_question(
                    segments[2], body.get("decision"), body.get("reviewed_answer")))
            return self._send_json(404, {"error": "Route not found"})
        except Exception as error:
            return self._handle_error(error)

    def do_PATCH(self):
        try:
            parts=self._segments();body=self._read_json();service=self.server.service.templates
            if len(parts)==4 and parts[:2]==["api","assignments"] and parts[3]=="exam-template":
                return self._send_json(200,self.server.service.teacher_workflow.update_draft(parts[2],body))
            if len(parts)==4 and parts[:3]==["api","templates","questions"]:
                return self._send_json(200,service.update_question(parts[3],body))
            if len(parts)==4 and parts[:3]==["api","templates","regions"]:
                return self._send_json(200,service.update_region(parts[3],body))
            return self._send_json(404,{"error":"Route not found"})
        except Exception as error:
            return self._handle_error(error)

    def do_DELETE(self):
        try:
            parts=self._segments();service=self.server.service.templates
            if len(parts)==4 and parts[:3]==["api","templates","questions"]:
                return self._send_json(200,service.delete_question(parts[3]))
            if len(parts)==4 and parts[:3]==["api","templates","regions"]:
                return self._send_json(200,service.delete_region(parts[3]))
            return self._send_json(404,{"error":"Route not found"})
        except Exception as error:
            return self._handle_error(error)

    def _send_image(self,mime,data):
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers();self.wfile.write(data)

    def log_message(self, format_string, *args):
        logger.info("%s - %s", self.address_string(), format_string % args)

    def _segments(self):
        path = urlsplit(self.path).path
        return [unquote(segment) for segment in path.strip("/").split("/") if segment]

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValidationError("Invalid Content-Length") from error
        if length > MAX_REQUEST_BYTES:
            raise ValidationError("Request body exceeds 15 MB")
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("Request body must be valid UTF-8 JSON") from error
        if not isinstance(body, dict):
            raise ValidationError("Request body must be a JSON object")
        return body

    def _send_json(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _cors_headers(self):
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _handle_error(self, error):
        status = _error_status(error)
        if status == 500:
            logger.exception("Local service request failed", exc_info=error)
        code = error.code if isinstance(error, DomainError) else {
            400: "VALIDATION_ERROR", 401: "UNAUTHORIZED", 404: "NOT_FOUND", 409: "INVALID_TRANSITION",
            413: "PAYLOAD_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE", 500: "INTERNAL_ERROR",
        }.get(status, "INTERNAL_ERROR")
        return self._send_json(status, {"error": str(error), "code": code})


def _error_status(error):
    if isinstance(error, DomainError):
        return error.status
    if isinstance(error, KeyError):
        return 404
    if isinstance(error, Unauthorized):
        return 401
    if isinstance(error, NotFound):
        return 404
    if isinstance(error, InvalidTransition):
        return 409
    if isinstance(error, PayloadTooLarge):
        return 413
    if isinstance(error, UnsupportedMediaType):
        return 415
    if isinstance(error, (ValidationError, ValueError)):
        return 400
    return 500


class CaptureHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service):
        self.service = service
        super().__init__(address, CaptureRequestHandler)
        self.expected_host = "{}:{}".format(*self.server_address[:2])
        self.expected_origin = "http://" + self.expected_host
        self.capture_page = Path(__file__).with_name("capture_page.html").read_bytes()


class CaptureRequestHandler(BaseHTTPRequestHandler):
    server_version = "MathGraderCapture/0.1"
    sys_version = ""

    def do_GET(self):
        try:
            self._check_surface()
            parsed = urlsplit(self.path)
            segments = self._segments()
            if segments == ["capture"]:
                values = parse_qs(parsed.query, keep_blank_values=True).get("t", [])
                if len(values) > 1:
                    raise Unauthorized("Capture Session token is invalid or no longer active")
                if values and values[0]:
                    self.server.service.authorized_capture_session(values[0])
                return self._send_bytes(200, self.server.capture_page, "text/html; charset=utf-8")
            if segments == ["api", "capture", "current"]:
                return self._send_json(200, self.server.service.current_capture(self._token()))
            if len(segments) == 5 and segments[:2] == ["api", "capture"] and segments[2] == "pages" and segments[4] == "image":
                content, mime_type = self.server.service.capture_page_image(
                    self._token(), segments[3]
                )
                return self._send_bytes(200, content, mime_type)
            return self._send_json(404, {"error": "Capture route not found"})
        except Exception as error:
            return self._handle_error(error)

    def do_POST(self):
        try:
            self._check_surface()
            segments = self._segments()
            if segments == ["api", "capture", "page"]:
                token = self._token()
                self.server.service.authorized_capture_session(token)
                submission_id = self.headers.get("X-Capture-Submission-ID", "")
                self.server.service.validate_capture_upload_target(token, submission_id)
                content_type = self.headers.get("Content-Type", "")
                filename = unquote(self.headers.get("X-File-Name", ""))
                upload_id = self.headers.get("Idempotency-Key", "")
                content = self._read_image()
                result = self.server.service.add_capture_uploaded_page(
                    token, filename, content_type, content, upload_id, submission_id
                )
                result["page"] = self._public_page(result["page"])
                return self._send_json(200 if result["idempotent"] else 201, result)
            if len(segments) == 5 and segments[:3] == ["api", "capture", "submissions"] and segments[4] == "finish":
                result = self.server.service.finish_capture_submission(
                    self._token(), segments[3]
                )
                return self._send_json(200 if result["already_finished"] else 202, result)
            return self._send_json(404, {"error": "Capture route not found"})
        except Exception as error:
            return self._handle_error(error)

    def do_DELETE(self):
        try:
            self._check_surface()
            segments = self._segments()
            if len(segments) == 4 and segments[:3] == ["api", "capture", "pages"]:
                state = self.server.service.delete_capture_page(self._token(), segments[3])
                return self._send_json(200, state)
            return self._send_json(404, {"error": "Capture route not found"})
        except Exception as error:
            return self._handle_error(error)

    def _check_surface(self):
        if self.headers.get("Host", "").lower() != self.server.expected_host.lower():
            raise _SurfaceForbidden("Host is not allowed")
        origin = self.headers.get("Origin")
        if origin and origin.rstrip("/") != self.server.expected_origin:
            raise _SurfaceForbidden("Origin is not allowed")
        if self.headers.get("Sec-Fetch-Site") in {"cross-site", "same-site"}:
            raise _SurfaceForbidden("Cross-origin Capture requests are not allowed")

    def _token(self):
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise Unauthorized("Capture Session token is invalid or no longer active")
        return authorization[7:]

    def _segments(self):
        return [unquote(segment) for segment in urlsplit(self.path).path.strip("/").split("/") if segment]

    def _read_image(self):
        if self.headers.get("Transfer-Encoding"):
            raise ValidationError("Chunked image uploads are not supported")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValidationError("Invalid Content-Length") from error
        if length < 1:
            raise ValidationError("Image must not be empty")
        if length > 10 * 1024 * 1024:
            if length <= 20 * 1024 * 1024:
                self.connection.settimeout(15)
                try:
                    drained = self.rfile.read(length)
                    if len(drained) != length:
                        self.close_connection = True
                except socket.timeout:
                    self.close_connection = True
                finally:
                    self.connection.settimeout(None)
            else:
                self.close_connection = True
            raise PayloadTooLarge("Image exceeds 10 MB")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValidationError("Image upload ended before the full file was received")
        return body

    @staticmethod
    def _public_page(page):
        return {
            key: page.get(key)
            for key in (
                "id", "submission_id", "page_index", "created_at", "original_filename",
                "mime_type", "byte_size", "uploaded_at",
            )
        }

    def _send_json(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return self._send_bytes(status, payload, "application/json; charset=utf-8")

    def _send_bytes(self, status, payload, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self' blob: data:; img-src 'self' blob: data:; "
            "connect-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _handle_error(self, error):
        status = 403 if isinstance(error, _SurfaceForbidden) else _error_status(error)
        if status == 500:
            logger.exception("Capture request failed", exc_info=error)
        return self._send_json(status, {"error": str(error)})

    def log_message(self, format_string, *args):
        # The QR token arrives in /capture?t=...; never write request targets to logs.
        return


class _SurfaceForbidden(Exception):
    pass


def create_capture_server(service, host, port=8766):
    return CaptureHTTPServer((host, port), service)


def create_server(service, host="127.0.0.1", port=8765, capture_bridge=None):
    is_loopback = host.lower() == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ValueError("Desktop admin API must bind to loopback")
    if capture_bridge is None:
        from local_service.capture_bridge import CaptureBridge

        capture_bridge = CaptureBridge(service)
    return ServiceHTTPServer((host, port), service, capture_bridge)
