import logging
from typing import List, Dict, Any
import httpx
from datetime import datetime

from python.db.models import Job
from python.scraper.base import BaseScraper
from python.utils.html_parser import clean_html

logger = logging.getLogger(__name__)

class AshbyScraper(BaseScraper):
    """
    Scraper implementation for companies using Ashby boards.
    Uses the Ashby public Job Postings API for custom career sites.
    """
    
    def __init__(self):
        self.source_name = "ashby"

    async def fetch_jobs(self, target: str) -> List[Job]:
        """
        Fetches job postings for a given company (job board name) from Ashby.
        
        Args:
            target: The job board name (e.g., 'warp', 'multi')
            
        Returns:
            A list of normalized Job Pydantic models.
        """
        url = f"https://api.ashbyhq.com/posting-api/job-board/{target}"
        logger.info(f"Fetching Ashby jobs from: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url)
                if response.status_code == 404:
                    logger.warning(f"Company/Job Board '{target}' not found on Ashby (404).")
                    return []
                response.raise_for_status()
                
                data = response.json()
                raw_jobs = data.get("jobs", [])
                
                company_name = target.replace("-", " ").title()
                
                normalized_jobs = []
                for raw_job in raw_jobs:
                    try:
                        job = self.normalize(raw_job, company_name)
                        normalized_jobs.append(job)
                    except Exception as ex:
                        logger.error(f"Error normalizing Ashby job {raw_job.get('id')}: {ex}")
                        
                logger.info(f"Successfully fetched and normalized {len(normalized_jobs)} jobs for {company_name}")
                return normalized_jobs
                
            except httpx.HTTPError as ex:
                logger.error(f"HTTP error fetching Ashby jobs for '{target}': {ex}")
                return []
            except Exception as ex:
                logger.error(f"Unexpected error fetching Ashby jobs for '{target}': {ex}")
                return []

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        """
        Normalizes raw Ashby job representation into a Job model.
        """
        external_id = str(raw.get("id"))
        title = raw.get("title", "").strip()
        
        # Extract location
        location_str = raw.get("location", "Unknown").strip()
        
        # Check if remote
        is_remote = False
        title_lower = title.lower()
        loc_lower = location_str.lower()
        
        # Extract additional metadata that might suggest remote status
        employment_type = str(raw.get("employmentType", "")).lower()
        secondary_locations = raw.get("secondaryLocations", [])
        
        if "remote" in loc_lower or "remote" in title_lower or "anywhere" in loc_lower or "remote" in employment_type:
            is_remote = True
            
        for sec_loc in secondary_locations:
            if isinstance(sec_loc, str) and "remote" in sec_loc.lower():
                is_remote = True
                break
            elif isinstance(sec_loc, dict) and "remote" in str(sec_loc.get("location", "")).lower():
                is_remote = True
                break

        url = raw.get("jobBoardUrl", f"https://jobs.ashbyhq.com/{company}/{external_id}")
        
        # Ashby jobs usually provide descriptionHtml or descriptionPlain
        raw_content = raw.get("descriptionHtml", raw.get("descriptionPlain", raw.get("description", "")))
        clean_jd = clean_html(raw_content)
        
        if not is_remote and clean_jd and ("remote" in clean_jd.lower()[:300] or "work from home" in clean_jd.lower()[:300]):
            is_remote = True

        # Extract posted date (Ashby uses publishedAt or updatedAt)
        posted_at_val = datetime.utcnow()
        published_at_str = raw.get("publishedAt")
        if published_at_str:
            try:
                posted_at_val = datetime.fromisoformat(published_at_str)
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
