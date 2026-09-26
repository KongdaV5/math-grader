CREATE TABLE classes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE students (
    id TEXT PRIMARY KEY,
    class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE RESTRICT,
    student_no TEXT NOT NULL,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE (class_id, student_no)
);

CREATE TABLE assignments (
    id TEXT PRIMARY KEY,
    class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    assignment_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'CLOSED')),
    created_at TEXT NOT NULL
);

CREATE TABLE submissions (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL REFERENCES assignments(id) ON DELETE RESTRICT,
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN (
        'EMPTY', 'CAPTURING', 'READY', 'QUEUED', 'PROCESSING',
        'REVIEW_REQUIRED', 'COMPLETED', 'FAILED'
    )),
    page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
    error TEXT,
    created_at TEXT NOT NULL,
    finished_capture_at TEXT,
    completed_at TEXT,
    UNIQUE (assignment_id, student_id)
);

CREATE TABLE submission_pages (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    page_index INTEGER NOT NULL CHECK (page_index > 0),
    source_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (submission_id, page_index)
);

CREATE TABLE recognition_results (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    page_id TEXT NOT NULL REFERENCES submission_pages(id) ON DELETE CASCADE,
    text TEXT,
    normalized_candidate TEXT,
    confidence REAL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (page_id)
);

CREATE TABLE jobs (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    submission_id TEXT NOT NULL UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX idx_students_class_active ON students(class_id, active, name);
CREATE INDEX idx_assignments_class_date ON assignments(class_id, assignment_date DESC);
CREATE INDEX idx_submissions_assignment ON submissions(assignment_id, created_at);
CREATE INDEX idx_jobs_queue ON jobs(status, sequence);
