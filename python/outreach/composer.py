import json
import logging
from google import genai
from google.genai import types
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

EMAIL_PROMPT = """\
Write a cold outreach email from Parva Chaudhari to {contact_name} ({contact_title}) at {company}.

THEIR LINKEDIN:
Headline: {headline}
About: {about}
Recent experience: {recent_experience}

JOB CONTEXT:
- Role: {job_title}
- Team: {team_name}
- Key signals from JD: {key_signals}
- Relevant project: {relevant_project}
- Orbit: multi-tenant supply chain platform, GCP/FastAPI/Postgres, 24 Shopify stores, 66% sync speed improvement
- MindHive: open-source AI knowledge base, RAG, Gemini embeddings, pgvector, 75% latency reduction
- Portfolio: https://parvachaudhari.vercel.app
- GitHub: https://github.com/ParvaChaudhari

STRICT RULES:
- Subject: "My job search pipeline flagged {company} — here's why I applied"
- Opening line: "I built a Python pipeline to surface and qualify engineering roles — {company} scored high enough that I'm reaching out directly."
- Reference ONE specific thing from their background (headline or about) naturally in sentence 1
- Body: exactly 3 sentences after the opener
- Sentence 1: specific connection between their background + the team/role
- Sentence 2: one concrete metric from relevant_project
- Sentence 3: portfolio link + ask for 15 min
- Tone: direct, peer-to-peer, no fluff
- No "I am excited to" / "I hope this finds you well" / "I am passionate about"
- Do NOT make up details not in the profile

Return ONLY valid JSON: {{"subject": "...", "body": "..."}}
"""


class EmailComposer:
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self.client = genai.Client()

    async def compose(
        self,
        contact_name: str,
        contact_title: str,
        headline: str,
        about: str,
        recent_experience: str,
        company: str,
        job_title: str,
        team_name: str,
        key_signals: List[str],
        relevant_project: str,
    ) -> Dict[str, str]:
        """
        Compose a cold outreach email using the contact's full LinkedIn profile context.

        All fields are explicit — no dicts to pick apart here, the orchestrator
        extracts the relevant values and passes them directly.
        """
        try:
            prompt = EMAIL_PROMPT.format(
                contact_name=contact_name or "Hiring Manager",
                contact_title=contact_title or "Engineering Manager",
                headline=headline or "",
                about=(about or "")[:1500],          # cap to avoid token bloat
                recent_experience=recent_experience or "",
                company=company,
                job_title=job_title,
                team_name=team_name or "Engineering",
                key_signals=", ".join(key_signals) if key_signals else "",
                relevant_project=relevant_project or "Orbit",
            )

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            data = json.loads(response.text)
            logger.info(f"Email composed for {contact_name} at {company}")
            return data

        except Exception as e:
            logger.error(f"Error composing email for {company}: {e}")
            return {
                "subject": f"My job search pipeline flagged {company} — here's why I applied",
                "body": (
                    f"I built a Python pipeline to surface and qualify engineering roles"
                    f" — {company} scored high enough that I'm reaching out directly.\n\n"
                    f"I'd love to chat about the {job_title} role. Would you have 15 minutes?"
                ),
            }
