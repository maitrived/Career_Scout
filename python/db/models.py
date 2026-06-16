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
    page_fill: float | None = None
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


class Outreach(BaseModel):
    id: UUID | None = None
    job_id: UUID
    contact_name: str | None = None
    contact_title: str | None = None
    contact_email: str | None = None
    contact_linkedin: str | None = None
    contact_headline: str | None = None
    contact_about: str | None = None
    company_domain: str | None = None
    team_name: str | None = None
    email_subject: str | None = None
    email_body: str | None = None
    gmail_draft_id: str | None = None
    status: str = "pending"
    sent_at: datetime | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True
