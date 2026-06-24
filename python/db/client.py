import sqlite3
import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from python.db.models import Job, Score, ResumeVersion, Application

DB_PATH = os.path.join("data", "auto_applier.db")


def get_connection() -> sqlite3.Connection:
    """Returns a standard sqlite3 connection with Row factory enabled."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys support in SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    # WAL mode allows concurrent reads/writes without locking the whole file
    conn.execute("PRAGMA journal_mode = WAL;")
    # Wait up to 5s if another writer holds a lock before giving up
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_db():
    """Initializes the database schema using local SQLite compatibility rules."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Jobs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        external_id TEXT NOT NULL,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT,
        remote INTEGER, -- Boolean stored as 0 or 1
        url TEXT NOT NULL,
        raw_jd TEXT,
        scraped_at TEXT NOT NULL,
        posted_at TEXT,
        UNIQUE(source, external_id)
    );
    """)

    # Self-healing migration for existing databases
    cursor.execute("PRAGMA table_info(jobs)")
    cols = [row[1] for row in cursor.fetchall()]
    if "posted_at" not in cols:
        cursor.execute("ALTER TABLE jobs ADD COLUMN posted_at TEXT;")

    # 2. Scores table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scores (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        embedding_similarity REAL NOT NULL,
        overall_score REAL NOT NULL,
        tech_fit REAL NOT NULL,
        level_fit REAL NOT NULL,
        growth_signal REAL NOT NULL DEFAULT 0.0,
        culture_signal REAL NOT NULL,
        sponsorship_signal REAL NOT NULL DEFAULT 3.0,
        rationale TEXT NOT NULL,
        red_flags TEXT NOT NULL, -- JSON string list
        scored_at TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)

    # Self-healing migration for existing databases (Score table)
    cursor.execute("PRAGMA table_info(scores)")
    cols = [row[1] for row in cursor.fetchall()]
    if "growth_signal" not in cols:
        cursor.execute(
            "ALTER TABLE scores ADD COLUMN growth_signal REAL NOT NULL DEFAULT 0.0;"
        )
    if "sponsorship_signal" not in cols:
        cursor.execute(
            "ALTER TABLE scores ADD COLUMN sponsorship_signal REAL NOT NULL DEFAULT 3.0;"
        )

    # 3. Resume versions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS resume_versions (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        resume_md TEXT NOT NULL,
        cover_letter TEXT NOT NULL,
        pdf_path TEXT,
        cover_letter_pdf_path TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)

    # Self-healing migration for resume_versions: add cover_letter_pdf_path if missing
    cursor.execute("PRAGMA table_info(resume_versions)")
    rv_cols = [row[1] for row in cursor.fetchall()]
    if "cover_letter_pdf_path" not in rv_cols:
        cursor.execute(
            "ALTER TABLE resume_versions ADD COLUMN cover_letter_pdf_path TEXT;"
        )
    if "page_fill" not in rv_cols:
        cursor.execute(
            "ALTER TABLE resume_versions ADD COLUMN page_fill REAL;"
        )

    # 4. Applications table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        resume_version_id TEXT,
        status TEXT NOT NULL DEFAULT 'ready',
        applied_at TEXT,
        notes TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
        FOREIGN KEY (resume_version_id) REFERENCES resume_versions(id) ON DELETE SET NULL
    );
    """)

    conn.commit()
    conn.close()


# Automatically initialize on import
init_db()

# ==========================================
# Database CRUD Operations
# ==========================================


def save_job(job: Job) -> Job:
    """Inserts or updates a job. Employs ON CONFLICT to avoid duplicate external jobs."""
    conn = get_connection()
    cursor = conn.cursor()

    if not job.id:
        job.id = uuid.uuid4()
    if not job.scraped_at:
        job.scraped_at = datetime.now()  # local machine time

    scraped_at_str = (
        job.scraped_at.isoformat()
        if isinstance(job.scraped_at, datetime)
        else str(job.scraped_at)
    )
    posted_at_str = (
        job.posted_at.isoformat()
        if isinstance(job.posted_at, datetime)
        else (str(job.posted_at) if job.posted_at else None)
    )

    cursor.execute(
        """
    INSERT INTO jobs (id, source, external_id, company, title, location, remote, url, raw_jd, scraped_at, posted_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(source, external_id) DO NOTHING
    RETURNING id;
    """,
        (
            str(job.id),
            job.source,
            job.external_id,
            job.company,
            job.title,
            job.location,
            1 if job.remote else (0 if job.remote is not None else None),
            job.url,
            job.raw_jd,
            scraped_at_str,
            posted_at_str,
        ),
    )

    row = cursor.fetchone()
    if row:
        job.id = uuid.UUID(row["id"])
    else:
        cursor.execute(
            "SELECT id FROM jobs WHERE source = ? AND external_id = ?",
            (job.source, job.external_id)
        )
        existing = cursor.fetchone()
        if existing:
            job.id = uuid.UUID(existing["id"])

    conn.commit()
    conn.close()
    return job


def get_job(job_id: str) -> Optional[Job]:
    """Retrieves a job by its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (str(job_id),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    posted_at_val = None
    if row["posted_at"]:
        try:
            posted_at_val = datetime.fromisoformat(row["posted_at"])
        except Exception:
            pass

    return Job(
        id=uuid.UUID(row["id"]),
        source=row["source"],
        external_id=row["external_id"],
        company=row["company"],
        title=row["title"],
        location=row["location"],
        remote=bool(row["remote"]) if row["remote"] is not None else None,
        url=row["url"],
        raw_jd=row["raw_jd"],
        scraped_at=datetime.fromisoformat(row["scraped_at"]),
        posted_at=posted_at_val,
    )


def get_unscored_jobs(
    within_days: Optional[int] = None, company_slug: Optional[str] = None
) -> list[Job]:
    """Returns all jobs that haven't been scored yet, optionally filtered by posting age and company."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT j.* FROM jobs j
    LEFT JOIN scores s ON j.id = s.job_id
    WHERE s.job_id IS NULL
    """

    params = []
    if company_slug:
        # Assuming source config slug matching, or basic LIKE on company name
        # We'll fetch all and filter in python for safety since slug logic can be fuzzy
        pass

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    unscored_jobs = []
    for row in rows:
        # Filter by company slug if provided
        if company_slug:
            # Simple match against the company name (which is often similar to the slug)
            # Or if your db has a source/slug column use that. Here company name is safe fallback.
            if company_slug.lower() not in row["company"].lower().replace(" ", ""):
                continue

        posted_at_val = None
        if row["posted_at"]:
            try:
                posted_at_val = datetime.fromisoformat(row["posted_at"])
            except Exception:
                pass
        unscored_jobs.append(
            Job(
                id=uuid.UUID(row["id"]),
                source=row["source"],
                external_id=row["external_id"],
                company=row["company"],
                title=row["title"],
                location=row["location"],
                remote=bool(row["remote"]) if row["remote"] is not None else None,
                url=row["url"],
                raw_jd=row["raw_jd"],
                scraped_at=datetime.fromisoformat(row["scraped_at"]),
                posted_at=posted_at_val,
            )
        )

    if within_days is not None:
        limit_dt = datetime.utcnow() - timedelta(days=within_days)
        filtered_jobs = []
        for j in unscored_jobs:
            if j.posted_at:
                p_dt = j.posted_at
                if p_dt.tzinfo is not None:
                    # Convert to UTC and strip timezone info
                    p_dt = p_dt.astimezone(timezone.utc).replace(tzinfo=None)
                if p_dt >= limit_dt:
                    filtered_jobs.append(j)
        unscored_jobs = filtered_jobs

    return unscored_jobs


def save_score(score: Score) -> Score:
    """Saves a scoring result to the local DB."""
    conn = get_connection()
    cursor = conn.cursor()

    if not score.id:
        score.id = uuid.uuid4()
    if not score.scored_at:
        score.scored_at = datetime.utcnow()

    scored_at_str = (
        score.scored_at.isoformat()
        if isinstance(score.scored_at, datetime)
        else str(score.scored_at)
    )

    cursor.execute(
        """
    INSERT INTO scores (id, job_id, embedding_similarity, overall_score, tech_fit, level_fit, growth_signal, culture_signal, sponsorship_signal, rationale, red_flags, scored_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        embedding_similarity=excluded.embedding_similarity,
        overall_score=excluded.overall_score,
        tech_fit=excluded.tech_fit,
        level_fit=excluded.level_fit,
        growth_signal=excluded.growth_signal,
        culture_signal=excluded.culture_signal,
        sponsorship_signal=excluded.sponsorship_signal,
        rationale=excluded.rationale,
        red_flags=excluded.red_flags,
        scored_at=excluded.scored_at
    """,
        (
            str(score.id),
            str(score.job_id),
            score.embedding_similarity,
            score.overall_score,
            score.tech_fit,
            score.level_fit,
            score.growth_signal,
            score.culture_signal,
            getattr(score, "sponsorship_signal", 3.0),
            score.rationale,
            json.dumps(score.red_flags),
            scored_at_str,
        ),
    )
    conn.commit()
    conn.close()
    return score


def save_resume_version(rv: ResumeVersion) -> ResumeVersion:
    """Saves a tailored resume version."""
    conn = get_connection()
    cursor = conn.cursor()

    if not rv.id:
        rv.id = uuid.uuid4()
    if not rv.created_at:
        rv.created_at = datetime.utcnow()

    created_at_str = (
        rv.created_at.isoformat()
        if isinstance(rv.created_at, datetime)
        else str(rv.created_at)
    )

    cursor.execute(
        """
    INSERT INTO resume_versions (id, job_id, resume_md, cover_letter, pdf_path, cover_letter_pdf_path, page_fill, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        resume_md=excluded.resume_md,
        cover_letter=excluded.cover_letter,
        pdf_path=excluded.pdf_path,
        cover_letter_pdf_path=excluded.cover_letter_pdf_path,
        page_fill=excluded.page_fill,
        created_at=excluded.created_at
    """,
        (
            str(rv.id),
            str(rv.job_id),
            rv.resume_md,
            rv.cover_letter,
            rv.pdf_path,
            getattr(rv, "cover_letter_pdf_path", None),
            getattr(rv, "page_fill", None),
            created_at_str,
        ),
    )
    conn.commit()
    conn.close()
    return rv


def save_application(app: Application) -> Application:
    """Saves or updates an application tracking record."""
    conn = get_connection()
    cursor = conn.cursor()

    if not app.id:
        app.id = uuid.uuid4()
    if not app.updated_at:
        app.updated_at = datetime.utcnow()

    applied_at_str = (
        app.applied_at.isoformat()
        if isinstance(app.applied_at, datetime)
        else (str(app.applied_at) if app.applied_at else None)
    )
    updated_at_str = (
        app.updated_at.isoformat()
        if isinstance(app.updated_at, datetime)
        else str(app.updated_at)
    )

    cursor.execute(
        """
    INSERT INTO applications (id, job_id, resume_version_id, status, applied_at, notes, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        resume_version_id=excluded.resume_version_id,
        status=excluded.status,
        applied_at=excluded.applied_at,
        notes=excluded.notes,
        updated_at=excluded.updated_at
    """,
        (
            str(app.id),
            str(app.job_id),
            str(app.resume_version_id) if app.resume_version_id else None,
            app.status,
            applied_at_str,
            app.notes,
            updated_at_str,
        ),
    )
    conn.commit()
    conn.close()
    return app


def mark_applied(
    job_id: str, status: str = "applied", notes: Optional[str] = None
) -> bool:
    """Marks an application status (e.g. applied, rejected, offer) and updates timestamps."""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()

    cursor.execute(
        """
    UPDATE applications
    SET status = ?, 
        applied_at = CASE WHEN ? = 'applied' AND applied_at IS NULL THEN ? ELSE applied_at END,
        notes = COALESCE(?, notes),
        updated_at = ?
    WHERE job_id = ?
    """,
        (status, status, now_str, notes, now_str, str(job_id)),
    )

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


def get_application_by_job(job_id: str) -> Optional[Application]:
    """Retrieves an application tracking record by job ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT id, job_id, resume_version_id, status, applied_at, notes, updated_at 
    FROM applications 
    WHERE job_id = ?
    """,
        (str(job_id),),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return Application(
            id=uuid.UUID(row["id"]),
            job_id=uuid.UUID(row["job_id"]),
            resume_version_id=(
                uuid.UUID(row["resume_version_id"])
                if row["resume_version_id"]
                else None
            ),
            status=row["status"],
            applied_at=(
                datetime.fromisoformat(row["applied_at"]) if row["applied_at"] else None
            ),
            notes=row["notes"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
    return None


def get_ready_applications() -> list[dict[str, Any]]:
    """Lists all 'ready' applications with core job details and pdf pathways."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        a.id as app_id,
        j.id as job_id,
        j.company,
        j.title,
        j.url,
        s.overall_score,
        rv.pdf_path,
        rv.cover_letter
    FROM applications a
    JOIN jobs j ON a.job_id = j.id
    JOIN scores s ON j.id = s.job_id
    JOIN resume_versions rv ON a.resume_version_id = rv.id
    WHERE a.status = 'ready'
    ORDER BY s.overall_score DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_ready_applications_by_date(scraped_date: str) -> list[dict[str, Any]]:
    """Lists 'ready' applications where the job was scraped on a specific date.

    Args:
        scraped_date: Either 'today' or a date string in MM-DD-YYYY format (e.g. '06-18-2026').

    Returns:
        A list of dicts with job details, score, and pdf_path.
    """
    from datetime import date as _date, datetime as _datetime

    if scraped_date.lower() == "today":
        target_date = _date.today().isoformat()  # YYYY-MM-DD for DB LIKE match
    else:
        # Accept MM-DD-YYYY format
        try:
            parsed = _datetime.strptime(scraped_date, "%m-%d-%Y")
            target_date = parsed.strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"Invalid date '{scraped_date}'. Use 'today' or MM-DD-YYYY format (e.g. '06-18-2026')."
            )

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT
        a.id as app_id,
        j.id as job_id,
        j.company,
        j.title,
        j.url,
        j.scraped_at,
        s.overall_score,
        rv.pdf_path,
        rv.cover_letter
    FROM applications a
    JOIN jobs j ON a.job_id = j.id
    JOIN scores s ON j.id = s.job_id
    JOIN resume_versions rv ON a.resume_version_id = rv.id
    WHERE a.status = 'ready'
      AND j.scraped_at LIKE ?
    ORDER BY s.overall_score DESC
    """,
        (f"{target_date}%",),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_jobs_needing_tailor() -> list[dict]:

    """Returns all scored jobs (>= 3.5) that don't yet have a tailored resume version."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT j.id, j.company, j.title, s.overall_score
    FROM jobs j
    JOIN scores s ON j.id = s.job_id
    LEFT JOIN applications a ON j.id = a.job_id
    LEFT JOIN resume_versions rv ON a.resume_version_id = rv.id
    WHERE s.overall_score >= 3.5
      AND (a.id IS NULL OR rv.resume_md IS NULL)
    ORDER BY s.overall_score DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_jobs_needing_package() -> list[dict]:
    """Returns all jobs with a tailored resume but no PDF yet."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT j.id, j.company, j.title, s.overall_score
    FROM jobs j
    JOIN scores s ON j.id = s.job_id
    JOIN applications a ON j.id = a.job_id
    JOIN resume_versions rv ON a.resume_version_id = rv.id
    WHERE (
        (rv.pdf_path IS NULL OR rv.pdf_path = '')
        OR (
            rv.cover_letter IS NOT NULL AND rv.cover_letter != ''
            AND (rv.cover_letter_pdf_path IS NULL OR rv.cover_letter_pdf_path = '')
        )
    )
    ORDER BY s.overall_score DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pipeline_status() -> dict[str, int]:
    """Generates dashboard metrics for visual rich print rendering."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Total jobs scraped
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_scraped = cursor.fetchone()[0]

    # 2. Total scored jobs
    cursor.execute("SELECT COUNT(*) FROM scores")
    total_scored = cursor.fetchone()[0]

    # 3. Jobs with score >= 3.5
    cursor.execute("SELECT COUNT(*) FROM scores WHERE overall_score >= 3.5")
    advanced = cursor.fetchone()[0]

    # 4. Status breakdown from applications
    cursor.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
    apps_by_status = {row["status"]: row[1] for row in cursor.fetchall()}

    conn.close()

    return {
        "scraped": total_scraped,
        "scored": total_scored,
        "advanced": advanced,
        "ready": apps_by_status.get("ready", 0),
        "applied": apps_by_status.get("applied", 0),
        "followed_up": apps_by_status.get("followed_up", 0),
        "responded": apps_by_status.get("responded", 0),
        "rejected": apps_by_status.get("rejected", 0),
        "offer": apps_by_status.get("offer", 0),
    }
