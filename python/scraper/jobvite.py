import httpx
import xmltodict
import logging
from typing import List, Dict, Any
from .base import BaseScraper
from python.db.models import Job
from python.config import TARGET_COMPANIES

logger = logging.getLogger(__name__)

class JobviteScraper(BaseScraper):
    source = "jobvite"
    BASE = "https://jobs.jobvite.com/api/job"

    async def fetch_jobs(self, target: str) -> List[Job]:
        company_info = next((c for c in TARGET_COMPANIES if c.get("slug") == target and c.get("source") == "jobvite"), None)
        company_name = company_info.get("name", target.title()) if company_info else target.title()
        
        all_jobs = []
        try:
            async with httpx.AsyncClient(timeout=15, verify=False) as client:
                r = await client.get(self.BASE, params={"c": target})
                if r.status_code != 200:
                    logger.warning(f"Jobvite API returned {r.status_code} for {target}")
                    return []
                    
                parsed = xmltodict.parse(r.text)
                jobs_raw = parsed.get("result", {}).get("job", [])
                
                # xmltodict returns a dict if there's only one job, so ensure it's a list
                if isinstance(jobs_raw, dict):
                    jobs_raw = [jobs_raw]
                    
                if not jobs_raw:
                    logger.warning(f"Company '{target}' not found on Jobvite (0 jobs returned).")
                    return []
                    
                for raw in jobs_raw:
                    job_model = self.normalize(raw, company_name)
                    all_jobs.append(job_model)
                    
        except Exception as ex:
            logger.error(f"Error fetching Jobvite jobs for {target}: {ex}")
            
        return all_jobs

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        location = raw.get("location", "")
        if isinstance(location, dict):
            location = ", ".join(filter(None, [location.get("city"), location.get("state"), location.get("country")]))
            
        return Job(
            source=self.source,
            external_id=raw.get("@id", raw.get("id", "")),
            company=company,
            title=raw.get("title", ""),
            location=location,
            remote="remote" in str(location).lower(),
            url=raw.get("apply-url", ""),
            raw_jd=raw.get("description", "")
        )
