-- Preserve P1-P3 rows while allowing multiple runs and generic sequential work.
ALTER TABLE submission_pages ADD COLUMN processed_image TEXT;
ALTER TABLE submission_pages ADD COLUMN processing_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(processing_status IN ('PENDING','PROCESSING','READY','WARNING','FAILED'));
ALTER TABLE submission_pages ADD COLUMN processing_started_at TEXT;
ALTER TABLE submission_pages ADD COLUMN processing_completed_at TEXT;
ALTER TABLE submission_pages ADD COLUMN page_detected INTEGER;
ALTER TABLE submission_pages ADD COLUMN perspective_corrected INTEGER;
ALTER TABLE submission_pages ADD COLUMN blur_score REAL;
ALTER TABLE submission_pages ADD COLUMN exposure_score REAL;
ALTER TABLE submission_pages ADD COLUMN transform_metadata TEXT;
ALTER TABLE submission_pages ADD COLUMN processing_warning TEXT;
ALTER TABLE submission_pages ADD COLUMN processing_error TEXT;
ALTER TABLE submission_pages ADD COLUMN template_binding_id TEXT;
CREATE TABLE template_bindings (
 id TEXT PRIMARY KEY, submission_page_id TEXT NOT NULL REFERENCES submission_pages(id) ON DELETE CASCADE,
 page_template_id TEXT NOT NULL, template_version INTEGER NOT NULL, snapshot_json TEXT NOT NULL,
 processed_image TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE answer_crops (
 id TEXT PRIMARY KEY, submission_page_id TEXT NOT NULL REFERENCES submission_pages(id) ON DELETE CASCADE,
 binding_id TEXT NOT NULL REFERENCES template_bindings(id), page_template_id TEXT NOT NULL,
 template_version INTEGER NOT NULL, question_id TEXT NOT NULL, answer_region_id TEXT NOT NULL,
 question_no TEXT NOT NULL, answer_type TEXT NOT NULL, region_index INTEGER NOT NULL,
 crop_path TEXT NOT NULL, normalized_bbox TEXT NOT NULL, pixel_bbox TEXT NOT NULL,
 width INTEGER NOT NULL CHECK(width>0), height INTEGER NOT NULL CHECK(height>0), created_at TEXT NOT NULL
);
CREATE TABLE recognition_results_v4 (
 id TEXT PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
 page_id TEXT NOT NULL REFERENCES submission_pages(id) ON DELETE CASCADE,
 text TEXT, normalized_candidate TEXT, confidence REAL, provider TEXT NOT NULL, model TEXT NOT NULL,
 latency_ms INTEGER NOT NULL, metadata_json TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL,
 crop_id TEXT REFERENCES answer_crops(id) ON DELETE CASCADE, page_template_id TEXT,
 template_version INTEGER, question_id TEXT, answer_region_id TEXT, region_index INTEGER,
 crop_path TEXT, model_revision TEXT, status TEXT NOT NULL DEFAULT 'SUCCESS', error_code TEXT,
 completed_at TEXT
);
INSERT INTO recognition_results_v4(id,submission_id,page_id,text,normalized_candidate,confidence,provider,model,latency_ms,metadata_json,error,created_at,status)
SELECT id,submission_id,page_id,text,normalized_candidate,confidence,provider,model,latency_ms,metadata_json,error,created_at,CASE WHEN error IS NULL THEN 'SUCCESS' ELSE 'FAILED' END FROM recognition_results;
DROP TABLE recognition_results;
ALTER TABLE recognition_results_v4 RENAME TO recognition_results;
CREATE INDEX idx_runs_crop ON recognition_results(crop_id,created_at);
CREATE TABLE jobs_v4 (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 submission_id TEXT UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','COMPLETED','FAILED')),
 error TEXT, created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT,
 kind TEXT NOT NULL DEFAULT 'SUBMISSION' CHECK(kind IN ('SUBMISSION','IMAGE','RECOGNITION')),
 page_id TEXT REFERENCES submission_pages(id) ON DELETE CASCADE,
 run_id TEXT REFERENCES recognition_results(id) ON DELETE CASCADE
);
INSERT INTO jobs_v4(sequence,id,submission_id,status,error,created_at,started_at,completed_at)
SELECT sequence,id,submission_id,status,error,created_at,started_at,completed_at FROM jobs;
DROP TABLE jobs;
ALTER TABLE jobs_v4 RENAME TO jobs;
CREATE INDEX idx_jobs_queue ON jobs(status,sequence);
CREATE UNIQUE INDEX idx_active_image_job ON jobs(page_id) WHERE kind='IMAGE' AND status IN ('QUEUED','RUNNING');
