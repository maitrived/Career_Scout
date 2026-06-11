import os
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

# Define Pydantic schema for structured Gemini output
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
    Evaluator that leverages Gemini 3 Flash to perform a deep rubric-based structured scoring
    on job descriptions compared against Parva's resume.
    """
    
    def __init__(self):
        # Gemini Code (Commented Out)
        # self.api_key = GEMINI_API_KEY
        # if not self.api_key:
        #     raise ValueError("GEMINI_API_KEY not found in environment configurations.")
        # self.client = genai.Client(api_key=self.api_key)
        # self.model_name = "gemini-3-flash-preview"

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
        # Load resume.json as structured preferences
        self.resume_json = self._load_resume_json()

    def _load_resume_json(self) -> dict:
        """Load `data/resume.json` to access structured preferences like relocation."""
        try:
            resume_path = Path("data/resume.json")
            if not resume_path.exists():
                resume_path = Path(__file__).resolve().parent.parent.parent / "data" / "resume.json"
            if resume_path.exists():
                return json.loads(resume_path.read_text(encoding="utf-8"))
        except Exception as ex:
            logger.debug(f"Could not load resume.json: {ex}")
        return {}

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
        """Loads Parva's markdown resume as a source of truth for LLM evaluation."""
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
                return "Parva: Python Backend Software Engineer, 2 YOE, GCP, FastAPI, PostgreSQL."
        except Exception as ex:
            logger.error(f"Error loading resume context file: {ex}")
            return ""

    def evaluate_job(self, job: Job) -> Score:
        """
        Runs LLM evaluation on a single job description.
        Computes overall score programmatically based on weighted rubric dimensions.
        """
        # Formulate prompt
        prompt = f"""
You are an expert technical recruiter analyzing a job posting for candidate Parva.
Evaluate the following Job Posting against Parva's Resume.

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
   - `tech_fit`: Rate alignment with Parva's stack (Python, FastAPI, PostgreSQL, Supabase, GCP, APIs, JWT/OAuth2). C#/.NET and Docker are secondary but solid. Low score for frontend (React-only) or non-matching backend frameworks (Java/Go/Ruby/PHP/Node).
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

        # Gemini Execution (Commented Out)
        # config = types.GenerateContentConfig(
        #     response_mime_type="application/json",
        #     response_schema=LLMScoreOutput,
        #     thinking_config=types.ThinkingConfig(
        #         thinking_level="minimal" 
        #     )
        # )
        # try:
        #     response = self.client.models.generate_content(
        #         model=self.model_name,
        #         contents=prompt,
        #         config=config
        #     )
        #     raw_text = response.text
        #     output = LLMScoreOutput.model_validate_json(raw_text)

        # NVIDIA NIM Execution
        try:
            raw_text = self._create_completion(prompt)
            output = LLMScoreOutput.model_validate_json(raw_text)

            # If candidate is willing to relocate, treat culture_signal as perfect (5.0)
            try:
                willing = bool(self.resume_json.get("willing_to_relocate", False))
            except Exception:
                willing = False
            if willing:
                culture_signal_val = 5.0
            else:
                culture_signal_val = output.culture_signal

            # If willing to relocate, remove location-related red flags produced by the LLM
            filtered_red_flags = []
            try:
                raw_flags = output.red_flags or []
                if willing:
                    for rf in raw_flags:
                        rf_lower = str(rf).lower()
                        if any(k in rf_lower for k in ["onsite", "on-site", "location", "located", "commute"]):
                            # drop this flag because candidate is willing to relocate
                            continue
                        filtered_red_flags.append(rf)
                else:
                    filtered_red_flags = raw_flags
            except Exception:
                filtered_red_flags = output.red_flags

            # Calculate overall score programmatically based on rubric weights:
            # - tech_fit: 35%
            # - level_fit: 25%
            # - growth_signal: 20%
            # - culture_signal: 20%
            overall = (
                (output.tech_fit * 0.35) + 
                (output.level_fit * 0.25) + 
                (output.growth_signal * 0.20) + 
                (culture_signal_val * 0.20)
            )
            
            # Round overall score to 2 decimal places
            overall = round(overall, 2)
            
            # If red flags exist (other than ["None"]), force overall score down to cap at 3.0 to prevent advancement
            has_red_flags = len(filtered_red_flags) > 0 and filtered_red_flags != ["None"] and filtered_red_flags != ["none"]
            if has_red_flags and overall >= 3.5:
                overall = 3.0
                
            return Score(
                job_id=job.id,
                embedding_similarity=0.0,  # Embedding step bypassed
                overall_score=overall,
                tech_fit=output.tech_fit,
                level_fit=output.level_fit,
                growth_signal=output.growth_signal,
                culture_signal=culture_signal_val,
                rationale=output.rationale,
                red_flags=filtered_red_flags
            )
            
        except Exception as ex:
            logger.error(f"Error calling Gemini evaluator for job '{job.title}' ({job.id}): {ex}")
            # Fallback score indicating failure
            return Score(
                job_id=job.id,
                embedding_similarity=0.0,
                overall_score=1.0,
                tech_fit=1.0,
                level_fit=1.0,
                growth_signal=1.0,
                culture_signal=1.0,
                rationale=f"Evaluation failed due to an error: {str(ex)}",
                red_flags=["EvaluationError"]
            )
