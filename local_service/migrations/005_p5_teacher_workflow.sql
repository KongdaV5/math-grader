ALTER TABLE assignments ADD COLUMN workflow_mode TEXT NOT NULL DEFAULT 'LEGACY'
    CHECK (workflow_mode IN ('LEGACY', 'TEACHER_WORKFLOW'));
ALTER TABLE submissions ADD COLUMN score REAL;
ALTER TABLE submissions ADD COLUMN max_score REAL;
ALTER TABLE submissions ADD COLUMN review_completed_at TEXT;
ALTER TABLE template_groups ADD COLUMN assignment_id TEXT REFERENCES assignments(id) ON DELETE CASCADE;
ALTER TABLE template_groups ADD COLUMN temporary INTEGER NOT NULL DEFAULT 0
    CHECK (temporary IN (0, 1));

CREATE UNIQUE INDEX idx_temporary_template_assignment
    ON template_groups(assignment_id) WHERE assignment_id IS NOT NULL;

CREATE TABLE assignment_exam_templates (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL UNIQUE REFERENCES assignments(id) ON DELETE CASCADE,
    template_group_id TEXT REFERENCES template_groups(id) ON DELETE RESTRICT,
    source_submission_id TEXT REFERENCES submissions(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'CONFIRMED')),
    draft_json TEXT NOT NULL,
    analysis_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT
);

CREATE TABLE question_results (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    page_id TEXT REFERENCES submission_pages(id) ON DELETE SET NULL,
    template_question_id TEXT REFERENCES template_questions(id) ON DELETE RESTRICT,
    question_no TEXT NOT NULL,
    answer_type TEXT NOT NULL,
    recognition_result_id TEXT REFERENCES recognition_results(id) ON DELETE SET NULL,
    expected_answer TEXT,
    accepted_answers_json TEXT NOT NULL DEFAULT '[]',
    student_answer TEXT,
    confidence REAL,
    decision_status TEXT NOT NULL CHECK (decision_status IN ('CORRECT', 'INCORRECT', 'REVIEW_REQUIRED')),
    review_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (review_status IN ('PENDING', 'DONE')),
    reviewed_answer TEXT,
    awarded_score REAL NOT NULL DEFAULT 0,
    max_score REAL NOT NULL CHECK (max_score >= 0),
    rule_code TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    UNIQUE (submission_id, template_question_id)
);

CREATE INDEX idx_question_results_review
    ON question_results(review_status, submission_id);
CREATE INDEX idx_question_results_submission
    ON question_results(submission_id, question_no);

CREATE TABLE jobs_v5 (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    submission_id TEXT UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    kind TEXT NOT NULL DEFAULT 'SUBMISSION'
        CHECK (kind IN ('SUBMISSION', 'IMAGE', 'RECOGNITION', 'GRADING')),
    page_id TEXT REFERENCES submission_pages(id) ON DELETE CASCADE,
    run_id TEXT REFERENCES recognition_results(id) ON DELETE CASCADE
);

INSERT INTO jobs_v5(sequence, id, submission_id, status, error, created_at, started_at,
                    completed_at, kind, page_id, run_id)
SELECT sequence, id, submission_id, status, error, created_at, started_at,
       completed_at, kind, page_id, run_id FROM jobs;
DROP TABLE jobs;
ALTER TABLE jobs_v5 RENAME TO jobs;
CREATE INDEX idx_jobs_queue ON jobs(status, sequence);
CREATE UNIQUE INDEX idx_active_image_job ON jobs(page_id)
    WHERE kind = 'IMAGE' AND status IN ('QUEUED', 'RUNNING');
