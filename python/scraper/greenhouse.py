import logging
from typing import List, Dict, Any
import httpx
from datetime import datetime

from python.db.models import Job
from python.scraper.base import BaseScraper
from python.utils.html_parser import clean_html

logger = logging.getLogger(__name__)

class GreenhouseScraper(BaseScraper):
    """
    Scraper implementation for companies using Greenhouse boards.
    Uses the Greenhouse public boards API.
    """
    
    def __init__(self):
        self.source_name = "greenhouse"

    async def fetch_jobs(self, target: str) -> List[Job]:
        """
        Fetches job postings for a given company slug from Greenhouse.
        
        Args:
            target: The company slug (e.g., 'anthropic', 'retargetly')
            
        Returns:
            A list of normalized Job Pydantic models.
        """
        url = f"https://boards-api.greenhouse.io/v1/boards/{target}/jobs?content=true"
        logger.info(f"Fetching Greenhouse jobs from: {url}")
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            try:
                response = await client.get(url)
                if response.status_code == 404:
                    logger.warning(f"Company '{target}' not found on Greenhouse (404).")
                    return []
                response.raise_for_status()
                
                data = response.json()
                raw_jobs = data.get("jobs", [])
                
                # Retrieve company display name if available, fallback to target slug capitalized
                meta = data.get("meta", {})
                company_name = meta.get("name", target.replace("-", " ").title())
                
                normalized_jobs = []
                for raw_job in raw_jobs:
                    try:
                        job = self.normalize(raw_job, company_name)
                        normalized_jobs.append(job)
                    except Exception as ex:
                        logger.error(f"Error normalizing Greenhouse job {raw_job.get('id')}: {ex}")
                        
                logger.info(f"Successfully fetched and normalized {len(normalized_jobs)} jobs for {company_name}")
                return normalized_jobs
                
            except httpx.HTTPError as ex:
                logger.error(f"HTTP error fetching Greenhouse jobs for '{target}': {ex}")
                return []
            except Exception as ex:
                logger.error(f"Unexpected error fetching Greenhouse jobs for '{target}': {ex}")
                return []

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        """
        Normalizes raw Greenhouse job representation into a Job model.
        """
        external_id = str(raw.get("id"))
        title = raw.get("title", "").strip()
        
        # Extract location
        loc_data = raw.get("location", {})
        location_str = loc_data.get("name", "Unknown").strip() if isinstance(loc_data, dict) else str(loc_data)
        
        # Check if remote
        is_remote = False
        title_lower = title.lower()
        loc_lower = location_str.lower()
        
        if "remote" in loc_lower or "remote" in title_lower or "anywhere" in loc_lower:
            is_remote = True
        
        url = raw.get("absolute_url", f"https://boards.greenhouse.io/{company}/jobs/{external_id}")
        raw_content = raw.get("content", "")
        clean_jd = clean_html(raw_content)
        
        # If title or jd contains remote terms, set remote to True
        if not is_remote and clean_jd and ("remote" in clean_jd.lower()[:300] or "work from home" in clean_jd.lower()[:300]):
            is_remote = True

        # Extract posted date (Greenhouse uses updated_at)
        posted_at_val = datetime.utcnow()
        updated_at_str = raw.get("updated_at")
        if updated_at_str:
            try:
                posted_at_val = datetime.fromisoformat(updated_at_str)
            except Exception:
                pass

        return Job(
            source=self.source_name,
            external_id=external_id,
            company=company,
            title=title,
            location=location_str,
            remote=is_remote,
            url=url,
            raw_jd=clean_jd,
            scraped_at=datetime.utcnow(),
            posted_at=posted_at_val
        )
