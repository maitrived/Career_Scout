import json
import logging
from pathlib import Path
from typing import List, Optional
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

from python.config import GEMINI_API_KEY, NIM_API_KEY, LLM_MODEL
from python.db.models import Job

logger = logging.getLogger(__name__)

# Pydantic schemas representing the exact structure of Parva's resume
class Contact(BaseModel):
    email: str
    phone: str
    location: str
    linkedin: str
    github: str
    portfolio: str

class EducationEntry(BaseModel):
    institution: str
    degree: str
    gpa: str
    location: str
    graduation_date: str

class Skills(BaseModel):
    languages: List[str]
    frameworks: List[str]
    databases: List[str]
    infrastructure: List[str]
    security: List[str]
    ai_ml: List[str]

class ExperienceEntry(BaseModel):
    company: str
    role: str
    location: str
    start_date: str
    end_date: str
    bullets: List[str]

class ProjectEntry(BaseModel):
    name: str
    role: str
    location: str
    start_date: str
    end_date: str
    link: Optional[str] = ""
    bullets: List[str]

class TailoredResume(BaseModel):
    name: str
    title: str
    contact: Contact
    summary: str
    education: List[EducationEntry]
    skills: Skills
    experience: List[ExperienceEntry]
    projects: List[ProjectEntry]

class ResumeTailor:
    """
    Handles tailoring Parva's resume to a specific job description.
    Outputs both structured JSON and clean Markdown formats.
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
        
        self.base_resume_data = self._load_base_resume()

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
            temperature=0.3,
            max_tokens=4096
        )
        return response.choices[0].message.content

    def _load_base_resume(self) -> dict:
        """Loads base resume JSON data as source of truth."""
        try:
            resume_path = Path("data/resume.json")
            if not resume_path.exists():
                resume_path = Path(__file__).resolve().parent.parent.parent / "data" / "resume.json"
                
            if resume_path.exists():
                with open(resume_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                raise FileNotFoundError("Base resume.json was not found in data/ or root directory.")
        except Exception as ex:
            logger.error(f"Error reading base resume JSON: {ex}")
            raise ex

    def tailor(self, job: Job) -> dict:
        """
        Calls Gemini to reorder and rephrase bullets according to the JD.
        Returns a dictionary matching the TailoredResume schema.
        """
        prompt = f"""
You are an expert technical resume tailor. Your objective is to tailor the candidate's base resume
to align with the specified job posting while strictly adhering to visual page constraints.

---
### CANDIDATE BASE RESUME (JSON)
{json.dumps(self.base_resume_data, indent=2)}

---
### TARGET JOB DETAILS
- **Company:** {job.company}
- **Title:** {job.title}
- **Description:** {job.raw_jd}

---
### TAILORING INSTRUCTIONS
1. **Bullet Points (Experience & Projects)**:
   - Reorder bullet points within each role/project to lead with the achievements most relevant to the job posting.
   - Rephrase the bullet text slightly to mirror terminology used in the job description where it is truthful.
   - Emphasize **Orbit** for supply chain, logistics, microservices, and platform/infrastructure roles.
   - Emphasize **MindHive** for AI, ML, vector search (pgvector), RAG, and data pipeline roles.
2. **Strict Layout Constraints (Must be followed exactly)**:
   - **Professional Summary**: Maximum of 2 sentences.
   - **Vybd Experience Bullets**: Pick and tailor exactly 6 most relevant bullets (discard the rest).
   - **Evision Experience Bullets**: Pick and tailor exactly 6 most relevant bullets (discard the rest).
   - **MindHive Project Bullets**: Tailor exactly 3 bullets.
   - **Total Bullets**: Under no circumstances should the total number of bullets in the entire resume exceed 15.
3. **No Fabrication**:
   - Do NOT invent any skills, experience, projects, tools, metrics, or education. Keep all credentials truthful to the base resume.
   - Keep dates, contacts, degree names, and location fields exactly unchanged.
4. **Structured JSON**:
   - Return the full tailored resume matching the following JSON schema exactly.
   - Schema: {json.dumps(TailoredResume.model_json_schema(), indent=2)}
"""

        # Gemini Execution (Commented Out)
        # config = types.GenerateContentConfig(
        #     response_mime_type="application/json",
        #     response_schema=TailoredResume,
        # )
        # try:
        #     response = self.client.models.generate_content(
        #         model=self.model_name,
        #         contents=prompt,
        #         config=config
        #     )
        #     tailored_data = json.loads(response.text)
        #     return tailored_data

        # NVIDIA NIM Execution
        try:
            raw_text = self._create_completion(prompt)
            tailored_data = json.loads(raw_text)
            return tailored_data
            
        except Exception as ex:
            logger.error(f"Failed to call Gemini resume tailor: {ex}")
            # Fallback to base resume unmodified in case of failure
            return self.base_resume_data

    @staticmethod
    def to_markdown(r: dict) -> str:
        """
        Renders the tailored resume JSON dictionary to a clean, ATS-compliant Markdown string
        that perfectly mirrors the formatting of the LaTeX original using semantic HTML injection.
        """
        md = []
        md.append(f"# {r['name']}")
        
        # Contact header
        c = r['contact']
        md.append(f"\n{c['phone']} | {c['email']} | [LinkedIn]({c['linkedin']}) | [GitHub]({c['github']}) | [Portfolio]({c['portfolio']})")
        md.append("\n---")
        
        # Summary
        md.append("\n## SUMMARY")
        md.append(r['summary'])
        md.append("\n---")
        
        # Professional Experience
        md.append("\n## PROFESSIONAL EXPERIENCE")
        for i, exp in enumerate(r['experience']):
            if i > 0:
                md.append('\n<div class="item-gap"></div>')
            md.append(f'\n<div class="item-header"><div class="item-title"><strong>{exp["role"]}</strong></div><div class="item-date"><strong>{exp["start_date"]} - {exp["end_date"]}</strong></div></div>\n<div class="item-subtitle"><strong>{exp["company"]}</strong></div>\n')
            for bullet in exp['bullets']:
                md.append(f"- {bullet}")
                
        md.append("\n---")
        
        # Education
        md.append("\n## EDUCATION")
        for i, edu in enumerate(r['education']):
            if i > 0:
                md.append('\n<div class="item-gap"></div>')
            loc_str = f", {edu['location']}" if edu.get('location') else ""
            gpa_str = f"<br>GPA {edu['gpa']}" if edu.get('gpa') else ""
            md.append(f'\n<div class="item-header"><div class="item-title"><strong>{edu["degree"]}</strong><br>{edu["institution"]}{loc_str}</div><div class="item-date" style="text-align: right;"><strong>{edu["graduation_date"]}</strong>{gpa_str}</div></div>\n')
            
        md.append("\n---")
        
        # Project Experience
        md.append("\n## PROJECT EXPERIENCE")
        for i, proj in enumerate(r['projects']):
            if i > 0:
                md.append('\n<div class="item-gap"></div>')
            proj_title = proj['name']
            role_title = proj.get('role', 'Open Source')
            proj_link = proj.get('link', '')
            if proj_link:
                link_str = f' | <a href="{proj_link}">Link</a>'
            else:
                link_str = ''
            md.append(f'\n<div class="item-header"><div class="item-title"><strong>{proj_title} | {role_title}{link_str}</strong></div><div class="item-date"><strong>{proj["start_date"]}</strong></div></div>\n')
            for bullet in proj['bullets']:
                md.append(f"- {bullet}")
                
        md.append("\n---")
        
        # Technical Skills
        md.append("\n## TECHNICAL SKILLS")
        skills = r['skills']
        md.append(f"- **Languages:** {', '.join(skills['languages'])}")
        md.append(f"- **Frameworks:** {', '.join(skills['frameworks'])}")
        md.append(f"- **Databases:** {', '.join(skills['databases'])}")
        md.append(f"- **Cloud & Infra:** {', '.join(skills['infrastructure'])}")
        md.append(f"- **APIs & Integration:** {', '.join(skills['security'])}")
        md.append(f"- **AI/ML:** {', '.join(skills['ai_ml'])}")
        
        return "\n".join(md) + "\n"
