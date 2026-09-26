"""Single source of truth for Submission status transitions."""


class InvalidTransition(ValueError):
    pass


TRANSITIONS = {
    "EMPTY": {"CAPTURING"},
    "CAPTURING": {"READY"},
    "READY": {"QUEUED"},
    "QUEUED": {"PROCESSING", "FAILED"},
    "PROCESSING": {"QUEUED", "REVIEW_REQUIRED", "COMPLETED", "FAILED"},
    "REVIEW_REQUIRED": {"COMPLETED"},
    "FAILED": {"QUEUED"},
    "COMPLETED": set(),
}


def transition(connection, submission_id, target, now, error=None):
    row = connection.execute(
        "SELECT status FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    if row is None:
        raise KeyError("Submission not found: {}".format(submission_id))

    current = row["status"]
    if target not in TRANSITIONS.get(current, set()):
        raise InvalidTransition(
            "Submission {} cannot transition from {} to {}".format(
                submission_id, current, target
            )
        )

    finished_capture_at = now if target == "READY" else None
    completed_at = now if target == "COMPLETED" else None
    connection.execute(
        """UPDATE submissions
           SET status = ?,
               error = ?,
               finished_capture_at = COALESCE(?, finished_capture_at),
               completed_at = COALESCE(?, completed_at)
           WHERE id = ?""",
        (target, error, finished_capture_at, completed_at, submission_id),
    )
    return target
