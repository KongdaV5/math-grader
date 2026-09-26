CREATE TABLE template_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    grade TEXT NOT NULL,
    semester TEXT NOT NULL,
    book_name TEXT NOT NULL,
    publisher TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE page_templates (
    id TEXT PRIMARY KEY,
    template_group_id TEXT NOT NULL REFERENCES template_groups(id) ON DELETE RESTRICT,
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    name TEXT NOT NULL,
    reference_image TEXT,
    fingerprint TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (template_group_id, page_number, version)
);

CREATE TABLE template_questions (
    id TEXT PRIMARY KEY,
    page_template_id TEXT NOT NULL REFERENCES page_templates(id) ON DELETE RESTRICT,
    question_no TEXT NOT NULL,
    answer_type TEXT NOT NULL,
    correct_answer TEXT,
    accepted_answers_json TEXT NOT NULL DEFAULT '[]',
    score REAL NOT NULL DEFAULT 1 CHECK (score >= 0),
    knowledge_tag TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (page_template_id, question_no)
);

CREATE TABLE answer_regions (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES template_questions(id) ON DELETE RESTRICT,
    region_index INTEGER NOT NULL CHECK (region_index > 0),
    x REAL NOT NULL CHECK (x >= 0 AND x < 1),
    y REAL NOT NULL CHECK (y >= 0 AND y < 1),
    width REAL NOT NULL CHECK (width > 0 AND width <= 1),
    height REAL NOT NULL CHECK (height > 0 AND height <= 1),
    coordinate_space TEXT NOT NULL DEFAULT 'normalized' CHECK (coordinate_space = 'normalized'),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (question_id, region_index)
);

CREATE INDEX idx_page_templates_group ON page_templates(template_group_id, page_number);
CREATE INDEX idx_template_questions_page ON template_questions(page_template_id, question_no);
CREATE INDEX idx_answer_regions_question ON answer_regions(question_id, region_index);
