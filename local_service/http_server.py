from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from urllib.parse import unquote, urlsplit

from local_service.service import MathGraderService, NotFound, ValidationError
from local_service.state_machine import InvalidTransition


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

    def __init__(self, address, service):
        self.service = service
        super().__init__(address, ServiceRequestHandler)


class ServiceRequestHandler(BaseHTTPRequestHandler):
    server_version = "MathGraderLocal/0.1"

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        try:
            segments = self._segments()
            if segments == ["health"]:
                return self._send_json(200, self.server.service.health())
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
            return self._send_json(404, {"error": "Route not found"})
        except Exception as error:
            return self._handle_error(error)

    def do_POST(self):
        try:
            segments = self._segments()
            body = self._read_json()
            service = self.server.service
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
                        service.create_assignment(class_id, body.get("name"), body.get("date")),
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
            return self._send_json(404, {"error": "Route not found"})
        except Exception as error:
            return self._handle_error(error)

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
        if isinstance(error, NotFound):
            status = 404
        elif isinstance(error, InvalidTransition):
            status = 409
        elif isinstance(error, ValidationError):
            status = 400
        else:
            status = 500
            logger.exception("Local service request failed", exc_info=error)
        return self._send_json(status, {"error": str(error)})


def create_server(service, host="127.0.0.1", port=8765):
    return ServiceHTTPServer((host, port), service)
