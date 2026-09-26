"""Small, explicit CRUD layer for versioned page reference templates."""

from datetime import datetime, timezone
import json
import math
import sqlite3
import uuid

from local_service.errors import InvalidAnswerRegion, TemplateNotFound


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + " is required")
    return value.strip()


def _row(row):
    item = dict(row)
    for key in ("accepted_answers_json", "metadata_json"):
        if key in item:
            item[key[:-5]] = json.loads(item.pop(key))
    if "active" in item:
        item["active"] = bool(item["active"])
    return item


class TemplateService:
    def __init__(self, database):
        self.database = database

    def _require(self, connection, table, item_id):
        row = connection.execute("SELECT * FROM {} WHERE id = ?".format(table), (item_id,)).fetchone()
        if row is None:
            raise TemplateNotFound("{} not found: {}".format(table, item_id))
        return row

    def create_template_group(self, name, grade, semester, book_name, publisher=None):
        item_id, now = str(uuid.uuid4()), _now()
        with self.database.connection() as connection:
            connection.execute("""INSERT INTO template_groups
                (id,name,grade,semester,book_name,publisher,version,created_at,updated_at)
                VALUES (?,?,?,?,?,?,1,?,?)""",
                (item_id, _text(name, "name"), _text(grade, "grade"),
                 _text(semester, "semester"), _text(book_name, "book_name"), publisher, now, now))
        return self.get_template_group(item_id)

    def get_template_group(self, group_id):
        with self.database.connection() as connection:
            return _row(self._require(connection, "template_groups", group_id))

    def list_template_groups(self):
        with self.database.connection() as connection:
            return [_row(row) for row in connection.execute("SELECT * FROM template_groups ORDER BY created_at DESC, id")]

    def create_page_template(self, group_id, page_number, name, reference_image=None):
        if not isinstance(page_number, int) or isinstance(page_number, bool) or page_number <= 0:
            raise ValueError("page_number must be a positive integer")
        item_id, now = str(uuid.uuid4()), _now()
        try:
            with self.database.connection() as connection:
                self._require(connection, "template_groups", group_id)
                connection.execute("""INSERT INTO page_templates
                    (id,template_group_id,page_number,name,reference_image,version,active,created_at,updated_at)
                    VALUES (?,?,?,?,?,1,1,?,?)""",
                    (item_id, group_id, page_number, _text(name, "name"), reference_image, now, now))
        except sqlite3.IntegrityError as error:
            raise ValueError("Page number already exists in this template group") from error
        return self.get_page_template(item_id)

    def list_page_templates(self, group_id):
        with self.database.connection() as connection:
            self._require(connection, "template_groups", group_id)
            return [_row(row) for row in connection.execute(
                "SELECT * FROM page_templates WHERE template_group_id=? ORDER BY page_number,version", (group_id,))]

    def get_page_template(self, page_id):
        with self.database.connection() as connection:
            item = _row(self._require(connection, "page_templates", page_id))
        item["questions"] = self.list_questions(page_id)
        return item

    def set_reference_image(self, page_id, source_ref):
        with self.database.connection() as connection:
            self._require(connection, "page_templates", page_id)
            connection.execute("UPDATE page_templates SET reference_image=?,updated_at=? WHERE id=?",
                               (source_ref, _now(), page_id))
        return self.get_page_template(page_id)

    def create_question(self, page_id, question_no, answer_type, correct_answer=None,
                        accepted_answers=None, score=1, knowledge_tag=None, metadata=None):
        if not isinstance(score, (int, float)) or not math.isfinite(score) or score < 0:
            raise ValueError("score must be nonnegative")
        if accepted_answers is not None and (not isinstance(accepted_answers, list) or
                                              any(not isinstance(value, str) for value in accepted_answers)):
            raise ValueError("accepted_answers must be a list of strings")
        item_id = str(uuid.uuid4())
        try:
            with self.database.connection() as connection:
                self._require(connection, "page_templates", page_id)
                connection.execute("""INSERT INTO template_questions
                    (id,page_template_id,question_no,answer_type,correct_answer,accepted_answers_json,
                     score,knowledge_tag,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (item_id, page_id, _text(question_no, "question_no"), _text(answer_type, "answer_type"),
                     correct_answer, json.dumps(accepted_answers or []), score, knowledge_tag,
                     json.dumps(metadata or {}), _now()))
        except sqlite3.IntegrityError as error:
            raise ValueError("Question number already exists on this page") from error
        return self.get_question(item_id)

    def get_question(self, question_id):
        with self.database.connection() as connection:
            item = _row(self._require(connection, "template_questions", question_id))
        item["regions"] = self.list_answer_regions(question_id)
        return item

    def list_questions(self, page_id):
        with self.database.connection() as connection:
            self._require(connection, "page_templates", page_id)
            ids = [row[0] for row in connection.execute(
                "SELECT id FROM template_questions WHERE page_template_id=? ORDER BY question_no", (page_id,))]
        return [self.get_question(item_id) for item_id in ids]

    def create_answer_region(self, question_id, region_index, x, y, width, height, metadata=None):
        values = (x, y, width, height)
        if (not isinstance(region_index, int) or isinstance(region_index, bool) or region_index <= 0 or
            any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values) or
            x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1):
            raise InvalidAnswerRegion("Bounding box must fit normalized 0..1 space")
        item_id = str(uuid.uuid4())
        try:
            with self.database.connection() as connection:
                self._require(connection, "template_questions", question_id)
                connection.execute("""INSERT INTO answer_regions
                    (id,question_id,region_index,x,y,width,height,coordinate_space,metadata_json,created_at)
                    VALUES (?,?,?,?,?,? ,?,'normalized',?,?)""",
                    (item_id, question_id, region_index, x, y, width, height,
                     json.dumps(metadata or {}), _now()))
        except sqlite3.IntegrityError as error:
            raise InvalidAnswerRegion("Region index already exists") from error
        with self.database.connection() as connection:
            return _row(self._require(connection, "answer_regions", item_id))

    def list_answer_regions(self, question_id):
        with self.database.connection() as connection:
            self._require(connection, "template_questions", question_id)
            return [_row(row) for row in connection.execute(
                "SELECT * FROM answer_regions WHERE question_id=? ORDER BY region_index", (question_id,))]
