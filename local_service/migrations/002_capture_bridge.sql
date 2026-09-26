ALTER TABLE submission_pages ADD COLUMN original_filename TEXT;
ALTER TABLE submission_pages ADD COLUMN mime_type TEXT;
ALTER TABLE submission_pages ADD COLUMN byte_size INTEGER NOT NULL DEFAULT 0 CHECK (byte_size >= 0);
ALTER TABLE submission_pages ADD COLUMN uploaded_at TEXT;
ALTER TABLE submission_pages ADD COLUMN content_sha256 TEXT;
ALTER TABLE submission_pages ADD COLUMN client_upload_id TEXT;

CREATE UNIQUE INDEX idx_submission_pages_client_upload
    ON submission_pages(client_upload_id)
    WHERE client_upload_id IS NOT NULL;

CREATE TABLE capture_sessions (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL REFERENCES assignments(id) ON DELETE RESTRICT,
    token_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'ENDED', 'EXPIRED')),
    current_student_id TEXT REFERENCES students(id) ON DELETE RESTRICT,
    current_submission_id TEXT REFERENCES submissions(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX idx_capture_sessions_one_active
    ON capture_sessions(status)
    WHERE status = 'ACTIVE';

CREATE TABLE capture_session_submissions (
    session_id TEXT NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE RESTRICT,
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    PRIMARY KEY (session_id, submission_id),
    UNIQUE (session_id, student_id)
);

CREATE INDEX idx_capture_session_submissions_order
    ON capture_session_submissions(session_id, started_at, student_id);
