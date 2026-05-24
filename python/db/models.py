from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class Job(BaseModel):
    id: UUID | None = None
    source: str
    external_id: str
    company: str
    title: str
    location: str | None = None
    remote: bool | None = None
    url: str
    raw_jd: str | None = None
    scraped_at: datetime | None = None
    posted_at: datetime | None = None

    class Config:
        from_attributes = True


class Score(BaseModel):
    id: UUID | None = None
    job_id: UUID
    embedding_similarity: float
    overall_score: float
    tech_fit: float
    level_fit: float
    growth_signal: float
    culture_signal: float
    rationale: str
    red_flags: list[str] = Field(default_factory=list)
    scored_at: datetime | None = None

    class Config:
        from_attributes = True


class ResumeVersion(BaseModel):
    id: UUID | None = None
    job_id: UUID
    resume_md: str
    cover_letter: str
    pdf_path: str | None = None
    cover_letter_pdf_path: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class Application(BaseModel):
    id: UUID | None = None
    job_id: UUID
    resume_version_id: UUID | None = None
    status: str = "ready"
    applied_at: datetime | None = None
    notes: str | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
