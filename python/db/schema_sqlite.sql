-- SQLite Schema for Auto-Applier
-- Automatically initialized by python/db/client.py

-- 1. Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,              -- 'greenhouse' | 'lever' | 'ashby' | 'apify'
    external_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    remote INTEGER,                    -- Boolean stored as 0 (false) or 1 (true)
    url TEXT NOT NULL,
    raw_jd TEXT,
    scraped_at TEXT NOT NULL,          -- ISO 8601 string datetime
    UNIQUE(source, external_id)
);

-- 2. Scores table
CREATE TABLE IF NOT EXISTS scores (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    embedding_similarity REAL NOT NULL,
    overall_score REAL NOT NULL,       -- 1–5 (only advance >= 3.5)
    tech_fit REAL NOT NULL,
    level_fit REAL NOT NULL,
    culture_signal REAL NOT NULL,
    rationale TEXT NOT NULL,
    red_flags TEXT NOT NULL,           -- JSON array text: '["flag1", "flag2"]'
    scored_at TEXT NOT NULL,           -- ISO 8601 string datetime
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- 3. Resume versions table
CREATE TABLE IF NOT EXISTS resume_versions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    resume_md TEXT NOT NULL,
    cover_letter TEXT NOT NULL,
    pdf_path TEXT,
    created_at TEXT NOT NULL,          -- ISO 8601 string datetime
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- 4. Applications table
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    resume_version_id TEXT,
    status TEXT NOT NULL DEFAULT 'ready', -- ready | applied | followed_up | responded | rejected | offer
    applied_at TEXT,                   -- ISO 8601 string datetime or NULL
    notes TEXT,
    updated_at TEXT NOT NULL,          -- ISO 8601 string datetime
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (resume_version_id) REFERENCES resume_versions(id) ON DELETE SET NULL
);
