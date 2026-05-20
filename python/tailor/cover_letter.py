import logging
from pathlib import Path
# from google import genai
from openai import OpenAI, RateLimitError
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

from python.config import GEMINI_API_KEY, NIM_API_KEY, LLM_MODEL
from python.db.models import Job

logger = logging.getLogger(__name__)

class CoverLetterGenerator:
    """
    Generates a technical, direct, three-paragraph cover letter tailored to a job description.
    """
    
    def __init__(self):
        # Gemini Code (Commented Out)
        # self.api_key = GEMINI_API_KEY
        # if not self.api_key:
        #     raise ValueError("GEMINI_API_KEY not found in configuration.")
        # self.client = genai.Client(api_key=self.api_key)
        # self.model_name = "gemini-2.5-flash"

        # NVIDIA NIM Code
        self.api_key = NIM_API_KEY
        if not self.api_key:
            raise ValueError("NIM_API_KEY not found in configuration.")
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.api_key
        )
        self.model_name = LLM_MODEL
        
        self.resume_text = self._load_resume_text()

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
            temperature=0.3,
            max_tokens=1024
        )
        return response.choices[0].message.content

    def _load_resume_text(self) -> str:
        """Loads data/resume.md to provide context to the LLM."""
        try:
            resume_path = Path("data/resume.md")
            if not resume_path.exists():
                resume_path = Path(__file__).resolve().parent.parent.parent / "data" / "resume.md"
            if resume_path.exists():
                return resume_path.read_text(encoding="utf-8")
            return "Parva: Python Backend Software Engineer, 2 YOE, GCP, FastAPI, PostgreSQL."
        except Exception as ex:
            logger.error(f"Error loading resume context: {ex}")
            return ""

    def generate(self, job: Job) -> str:
        """Generates a technical, direct cover letter for the target job."""
        prompt = f"""
You are writing a professional, technical, and direct cover letter for candidate Parva Jignesh Chaudhari.

---
### CANDIDATE RESUME
{self.resume_text}

---
### TARGET JOB DETAILS
- **Company:** {job.company}
- **Title:** {job.title}
- **Description:** {job.raw_jd}

---
### COVER LETTER RULES
1. **Length**: Under 250 words total.
2. **Structure**: Exactly three paragraphs, formatted as plain text without any markdown or formatting.
   - **Paragraph 1 (Role & Context)**: Explain why you are applying to this specific role and company. Mention a concrete technical problem they are solving. Do NOT use generic openings like "I am excited to apply for..." or "I am writing to express my interest...". Open directly and professionally (e.g. "I am applying for the Software Engineer role at Vercel to work on identity management systems...").
   - **Paragraph 2 (Relevant Experience)**: Focus on the single most relevant engineering proof point in your history:
     - Emphasize **Orbit** (multi-tenant supply chain platform, GCP OIDC service-to-service auth, headless Odoo 18, Supabase RLS) for supply chain, logistics, microservices, and platform/infrastructure roles.
     - Emphasize **MindHive** (open-source AI personal knowledge base, FastAPI, Supabase, pgvector semantic search, Gemini embeddings, NVIDIA NIM, Queen Bee agent response optimizations) for AI, ML, search, and data pipeline roles.
   - **Paragraph 3 (One-Sentence Close)**: Write a brief close proposing a technical call. Do NOT write fluff like "I look forward to hearing from you" or "Thank you for your time and consideration." Make it direct, e.g. "I am available to discuss my experience with microservices and auth integrations at your convenience."
3. **Tone**: Direct, technical, and confident. Avoid passive voice or emotional fluff (no "passion", "excitement", "perfection").
4. **Output**: Return ONLY the cover letter text, with no headers, footers, subject lines, greeting templates, or markdown.
"""

        # Gemini Execution (Commented Out)
        # try:
        #     response = self.client.models.generate_content(
        #         model=self.model_name,
        #         contents=prompt
        #     )
        #     return response.text.strip()

        # NVIDIA NIM Execution
        try:
            return self._create_completion(prompt).strip()
        except Exception as ex:
            logger.error(f"Error calling cover letter generator: {ex}")
            # Fallback cover letter
            return f"Parva Jignesh Chaudhari\n\nI am applying for the {job.title} role at {job.company}. " \
                   f"My background is in Python, FastAPI, and GCP, where I recently architected a secure supply chain microservices platform. " \
                   f"I am available to discuss how my backend and infrastructure skills align with your engineering needs."
