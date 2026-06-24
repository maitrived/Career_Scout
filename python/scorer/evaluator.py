import os
import re
import logging
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel, Field
# from google import genai
# from google.genai import types
from openai import OpenAI, RateLimitError
import json
import tenacity

def is_rate_limit_error(exception):
    if isinstance(exception, RateLimitError):
        return True
    if hasattr(exception, "status_code") and exception.status_code == 429:
        return True
    err_str = str(exception).lower()
    if "429" in err_str or "too many requests" in err_str:
        return True
    return False

from python.db.models import Job, Score
from python.config import GEMINI_API_KEY, NIM_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

# ─── Sponsorship Pre-Scanner ──────────────────────────────────────────────────

# Phrases that explicitly state they will NOT sponsor
_NO_SPONSOR_PATTERNS = re.compile(
    r"("
    r"will\s+not\s+sponsor"
    r"|unable\s+to\s+(provide|offer|support)\s+(visa\s+)?sponsor"
    r"|does?\s+not\s+sponsor"
    r"|cannot\s+sponsor"
    r"|no\s+(visa\s+)?sponsor"
    r"|not\s+eligible\s+for\s+sponsor"
    r"|sponsorship\s+(is\s+)?not\s+(available|offered|provided)"
    r"|we\s+do\s+not\s+sponsor"
    r"|authorization\s+to\s+work\s+in\s+the\s+u\.?s\.?\s+without\s+sponsor"
    r"|must\s+be\s+(authorized|eligible)\s+to\s+work\s+without\s+sponsor"
    r"|candidates?\s+requiring\s+sponsor"
    r"|require\s+work\s+authorization\s+without\s+sponsorship"
    r")",
    re.IGNORECASE,
)

# Phrases that explicitly state they WILL sponsor
_WILL_SPONSOR_PATTERNS = re.compile(
    r"("
    r"will\s+sponsor"
    r"|offer(s|ing)?\s+(visa\s+)?sponsor"
    r"|provide(s|ing)?\s+(visa\s+)?sponsor"
    r"|support(s|ing)?\s+(visa\s+)?sponsor"
    r"|open\s+to\s+sponsor"
    r"|h[\-\s]?1b\s+sponsor"
    r"|visa\s+sponsor(ship)?\s+(is\s+)?(available|offered|provided|considered|possible)"
    r"|sponsor(s|ing)?\s+(work\s+)?(visa|visas|authorization)"
    r")",
    re.IGNORECASE,
)


def _score_sponsorship(raw_jd: str) -> tuple[float, str]:
    """
    Fast regex scan of the job description to determine visa sponsorship stance.

    Returns:
        (score, label) where score is 1.0 / 3.0 / 5.0 and label is a short string.
        - 1.0  -> explicit no-sponsor (hard reject signal)
        - 3.0  -> not mentioned (neutral -- assume possible)
        - 5.0  -> explicitly offers sponsorship
    """
    text = raw_jd or ""
    if _NO_SPONSOR_PATTERNS.search(text):
        return 1.0, "No sponsorship -- explicitly stated"
    if _WILL_SPONSOR_PATTERNS.search(text):
        return 5.0, "Sponsorship available -- explicitly stated"
    return 3.0, "Sponsorship not mentioned -- neutral"


# ─── LLM Score Schema ─────────────────────────────────────────────────────────

# Define Pydantic schema for structured LLM output
class LLMScoreOutput(BaseModel):
    tech_fit: float = Field(
        ..., 
        description="Score from 1.0 to 5.0 assessing technical stack match. "
                    "High score: Python, FastAPI, PostgreSQL, Supabase, GCP, microservices, APIs, JWT/OAuth2. "
                    "Medium score: C#/.NET Core MVC, Docker, Shopify APIs, Odoo. "
                    "Low score: React/frontend only, Java, PHP, Ruby, Go, or other unrelated backend frameworks."
    )
    level_fit: float = Field(
        ...,
        description="Score from 1.0 to 5.0 assessing level/experience match. "
                    "Target is ~2 YOE. 1.0-3.0 YOE is a perfect match (5.0). "
                    "Subtract points for 4+ YOE. If 5+ YOE is a hard requirement, or the role is senior/staff/lead, score must be <= 2.0."
    )
    growth_signal: float = Field(
        ...,
        description="Score from 1.0 to 5.0 assessing the learning/growth potential. "
                    "High score: AI/ML integrations, supply chain, platform/infrastructure, complex data pipelines. "
                    "Low score: basic CRUD applications, pure maintenance work, non-technical domains."
    )
    culture_signal: float = Field(
        ...,
        description="Score from 1.0 to 5.0 checking workplace/flexibility fit. "
                    "5.0: Fully Remote or located in Scottsdale/Phoenix/Tempe Arizona. "
                    "3.0-4.0: Hybrid in Arizona. "
                    "1.0-2.0: Non-remote positions outside of Arizona (e.g. strict onsite in SF, NY, etc.)."
    )
    rationale: str = Field(
        ...,
        description="Engineering-focused detailed technical explanation of the scoring decision, "
                    "listing specific technology matches, YOE requirements, flexibility status, and growth/rejection signals."
    )
    red_flags: List[str] = Field(
        default_factory=list,
        description="List of detected red flag strings (e.g. 'frontend', 'senior', 'security clearance', "
                    "'gambling/crypto/ad-tech', '5+ YOE'). Use ['None'] if no red flags are found."
    )

class JobEvaluator:
    """
    Evaluator that leverages an LLM to perform a deep rubric-based structured scoring
    on job descriptions compared against the candidate's resume.
    """
    
    def __init__(self):
        # NVIDIA NIM Code
        self.api_key = NIM_API_KEY
        if not self.api_key:
            raise ValueError("NIM_API_KEY not found in environment configurations.")
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.api_key
        )
        self.model_name = LLM_MODEL
        
        # Load resume context once during initialization
        self.resume_text = self._load_resume()

    @tenacity.retry(
        retry=tenacity.retry_if_exception(is_rate_limit_error),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        stop=tenacity.stop_after_attempt(5),
        reraise=True
    )
    def _create_completion(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1024
        )
        return response.choices[0].message.content

    def _load_resume(self) -> str:
        """Loads the candidate's markdown resume as a source of truth for LLM evaluation."""
        try:
            # Assume run from root workspace
            resume_path = Path("data/resume.md")
            if not resume_path.exists():
                # Try parent directory fallback
                resume_path = Path(__file__).resolve().parent.parent.parent / "data" / "resume.md"
                
            if resume_path.exists():
                return resume_path.read_text(encoding="utf-8")
            else:
                logger.warning("data/resume.md not found. Falling back to default profile description.")
                return "Maitri: Python/Java Backend Software Engineer, 2 YOE, GCP, FastAPI, PostgreSQL."
        except Exception as ex:
            logger.error(f"Error loading resume context file: {ex}")
            return ""

    def evaluate_job(self, job: Job) -> Score:
        """
        Runs LLM evaluation on a single job description.
        Computes overall score programmatically based on weighted rubric dimensions.

        Scoring weights:
          - tech_fit:            30%
          - level_fit:           22%
          - growth_signal:       18%
          - culture_signal:      15%
          - sponsorship_signal:  15%  <- pre-scan (no extra API call needed)
        """
        # ── Step 1: Fast sponsorship pre-scan (regex, no API call) ─────────────
        sponsorship_score, sponsorship_label = _score_sponsorship(job.raw_jd or "")
        logger.info(
            f"Sponsorship scan for '{job.title}' @ {job.company}: "
            f"{sponsorship_label} (score={sponsorship_score})"
        )

        # ── Step 2: Build LLM prompt ───────────────────────────────────────────
        prompt = f"""
You are an expert technical recruiter analyzing a job posting for the candidate.
Evaluate the following Job Posting against the Candidate's Resume.

---
### CANDIDATE RESUME (Source of Truth)
{self.resume_text}

---
### JOB POSTING
- **Company:** {job.company}
- **Title:** {job.title}
- **Location:** {job.location}
- **Remote:** {job.remote}
- **URL:** {job.url}

#### Description:
{job.raw_jd}

---
### EVALUATION INSTRUCTIONS & CRITERIA
1. Grade the job on the following four dimensions (1.0 to 5.0 scale):
   - `tech_fit`: Rate alignment with the candidate's technical stack as defined in their resume. High score for jobs demanding their primary skills. Low score for jobs requiring entirely different frameworks or languages.
   - `level_fit`: Target is ~2 Years of Experience. Rate 5.0 if YOE requirement is 1-3 years. If 5+ YOE is a hard requirement, or the role is a senior/staff/lead, rate <= 2.0.
   - `growth_signal`: Rate learning/growth opportunities in the problem space (AI/ML, supply chain, platforms, data pipelines).
   - `culture_signal`: Rate flexibility. 5.0 for fully remote or Arizona (Scottsdale/Phoenix/Tempe). Low score (1.0-2.0) for strict onsite positions outside of Arizona.

2. Check for the following Auto-Reject Red Flags:
   - Job title contains: "Frontend", "React Developer", "UI Engineer", "QA", "DevOps-only".
   - Hard requirement for 5+ years of experience.
   - Hard requirement for an active security clearance.
   - Company business domain is in: gambling, crypto trading, or pure ad-tech.
   If any of these conditions are met, list them in `red_flags` and ensure the scores are penalized so that the final calculated weighted overall score will fall below 3.5.

3. Complete the technical rationale with clear engineering facts. Do not fabricate experience.
4. Output MUST be a valid JSON object matching the following JSON schema:
{json.dumps(LLMScoreOutput.model_json_schema(), indent=2)}
"""

        # ── Step 3: Call LLM ───────────────────────────────────────────────────
        try:
            raw_text = self._create_completion(prompt)
            output = LLMScoreOutput.model_validate_json(raw_text)
            
            # ── Step 4: Weighted overall score ─────────────────────────────────
            # tech_fit 30% | level_fit 22% | growth_signal 18%
            # culture_signal 15% | sponsorship_signal 15%
            overall = (
                (output.tech_fit       * 0.30) +
                (output.level_fit      * 0.22) +
                (output.growth_signal  * 0.18) +
                (output.culture_signal * 0.15) +
                (sponsorship_score     * 0.15)
            )
            overall = round(overall, 2)

            # Build combined red flags list
            red_flags = list(output.red_flags)

            # ── Step 5: Hard-reject rules ───────────────────────────────────────
            has_llm_red_flags = (
                red_flags
                and red_flags != ["None"]
                and red_flags != ["none"]
            )

            # No-sponsor -> hard reject: cap score and add red flag
            if sponsorship_score == 1.0:
                if "No visa sponsorship" not in red_flags:
                    red_flags.append("No visa sponsorship")
                if overall >= 3.5:
                    overall = min(overall, 2.5)
                    logger.info(
                        f"Score capped to {overall} (no-sponsorship) "
                        f"for '{job.title}' @ {job.company}"
                    )

            # Other LLM red flags cap at 3.0
            elif has_llm_red_flags and overall >= 3.5:
                overall = 3.0
                
            return Score(
                job_id=job.id,
                embedding_similarity=0.0,  # Embedding step bypassed
                overall_score=overall,
                tech_fit=output.tech_fit,
                level_fit=output.level_fit,
                growth_signal=output.growth_signal,
                culture_signal=output.culture_signal,
                sponsorship_signal=sponsorship_score,
                rationale=f"[Sponsorship: {sponsorship_label}] {output.rationale}",
                red_flags=red_flags
            )
            
        except Exception as ex:
            logger.error(f"Error calling LLM evaluator for job '{job.title}' ({job.id}): {ex}")
            # Fallback score indicating failure
            return Score(
                job_id=job.id,
                embedding_similarity=0.0,
                overall_score=1.0,
                tech_fit=1.0,
                level_fit=1.0,
                growth_signal=1.0,
                culture_signal=1.0,
                sponsorship_signal=3.0,
                rationale=f"Evaluation failed due to an error: {str(ex)}",
                red_flags=["EvaluationError"]
            )
