import httpx
import logging
from typing import List, Dict, Any
from .base import BaseScraper
from python.db.models import Job
from python.config import TARGET_COMPANIES

logger = logging.getLogger(__name__)

class SmartRecruitersScraper(BaseScraper):
    source = "smartrecruiters"
    BASE = "https://api.smartrecruiters.com/v1/companies"

    async def fetch_jobs(self, target: str) -> List[Job]:
        company_info = next((c for c in TARGET_COMPANIES if c.get("slug") == target and c.get("source") == "smartrecruiters"), None)
        company_name = company_info.get("name", target.title()) if company_info else target.title()

        all_jobs = []
        offset = 0
        limit = 100
        
        try:
            async with httpx.AsyncClient(timeout=15, verify=False) as client:
                # 1. Fetch paginated list of jobs
                while True:
                    r = await client.get(
                        f"{self.BASE}/{target}/postings",
                        params={"limit": limit, "offset": offset}
                    )
                    
                    if r.status_code != 200:
                        logger.warning(f"SmartRecruiters API returned {r.status_code} for {target}: {r.text}")
                        break
                        
                    data = r.json()
                    jobs_raw = data.get("content", [])
                    
                    if not jobs_raw:
                        if offset == 0:
                            logger.warning(f"Company '{target}' not found on SmartRecruiters (0 jobs returned).")
                        break
                        
                    import asyncio
                    semaphore = asyncio.Semaphore(10)

                    async def fetch_detail(raw_job):
                        async with semaphore:
                            job_id = raw_job.get("id")
                            if job_id:
                                try:
                                    detail_r = await client.get(f"{self.BASE}/{target}/postings/{job_id}")
                                    if detail_r.status_code == 200:
                                        sections = detail_r.json().get("jobAd", {}).get("sections", {})
                                        # Concatenate all text sections
                                        full_text = " ".join(
                                            s.get("text", "") for s in sections.values() if isinstance(s, dict)
                                        )
                                        raw_job["jobDescription"] = full_text
                                    else:
                                        raw_job["jobDescription"] = ""
                                except Exception as ex:
                                    logger.error(f"Error fetching detail for job {job_id}: {ex}")
                                    raw_job["jobDescription"] = ""
                            else:
                                raw_job["jobDescription"] = ""
                            return raw_job

                    fetch_tasks = [fetch_detail(raw) for raw in jobs_raw]
                    completed_raw_jobs = await asyncio.gather(*fetch_tasks)

                    for raw in completed_raw_jobs:
                        job_model = self.normalize(raw, company_name)
                        all_jobs.append(job_model)
                        
                    if len(jobs_raw) < limit:
                        break
                        
                    offset += limit
                    
        except Exception as ex:
            logger.error(f"Error fetching SmartRecruiters jobs for {target}: {ex}")
            
        return all_jobs

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        location_obj = raw.get("location", {})
        location_str = location_obj.get("city", "")
        if location_obj.get("region"):
            location_str += f", {location_obj.get('region')}"
            
        return Job(
            source=self.source,
            external_id=raw["id"],
            company=company,
            title=raw.get("name", ""),
            location=location_str.strip(", "),
            remote=location_obj.get("remote", False),
            url=raw.get("ref", ""),
            raw_jd=raw.get("jobDescription", "")
        )
