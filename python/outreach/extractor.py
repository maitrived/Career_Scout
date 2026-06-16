import os
import json
import logging
from google import genai
from google.genai import types
from typing import Dict, Any

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """
You are given a job description for {company}. Extract the following as JSON:

1. team_name — the engineering team or sub-team name (e.g. "Platform Engineering", "Infrastructure", "Data")
2. manager_title_keywords — job title keywords to search for the hiring manager (e.g. "Engineering Manager", "Head of Platform"). Derive from context if not explicit.
3. company_domain — the company's website domain (e.g. "notion.com", "stripe.com"). Derive from the company name if the domain is not explicitly in the JD.
4. key_signals — specific, unique things about this role/team (max 2)
5. relevant_project — "Orbit" for supply chain/logistics/platform/ecommerce roles, "MindHive" for AI/ML/data/search roles, "both" if it touches both
6. linkedin_search_keyword — 2–4 words to find the hiring manager on LinkedIn's company people page.
   - Must target the manager/lead of this team, NOT the open role itself.
   - Must be team-specific (e.g. "engineering manager backend", "head of platform", "staff engineer infrastructure").
   - Must NOT be generic terms like "software engineer", "developer", or "AWS".
   - Will be used as the `?keywords=` param on the company LinkedIn /people page.

Respond with ONLY valid JSON:
{{
  "team_name": "...",
  "manager_title_keywords": ["..."],
  "company_domain": "...",
  "key_signals": ["..."],
  "relevant_project": "...",
  "linkedin_search_keyword": "..."
}}

JD: {jd}
"""

class JDExtractor:
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self.client = genai.Client()

    async def extract(self, raw_jd: str, company: str = "") -> Dict[str, Any]:
        try:
            prompt = EXTRACT_PROMPT.format(company=company, jd=raw_jd)
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            data = json.loads(response.text)
            logger.info(
                f"Extracted from JD: team_name={data.get('team_name')}, "
                f"domain={data.get('company_domain')}, "
                f"manager_keywords={data.get('manager_title_keywords')}, "
                f"linkedin_keyword={data.get('linkedin_search_keyword')!r}"
            )
            return data
        except Exception as e:
            logger.error(f"Error extracting JD details for outreach: {e}")
            return {
                "team_name": "Engineering",
                "manager_title_keywords": ["Engineering Manager", "Director of Engineering"],
                "company_domain": "",
                "key_signals": [],
                "relevant_project": "Orbit",
                "linkedin_search_keyword": "engineering manager backend"
            }
