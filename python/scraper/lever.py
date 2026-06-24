import logging
from typing import List, Dict, Any
import httpx
from datetime import datetime

from python.db.models import Job
from python.scraper.base import BaseScraper
from python.utils.html_parser import clean_html

logger = logging.getLogger(__name__)

class LeverScraper(BaseScraper):
    """
    Scraper implementation for companies using Lever boards.
    Uses the Lever public postings API.
    """
    
    def __init__(self):
        self.source_name = "lever"

    async def fetch_jobs(self, target: str) -> List[Job]:
        """
        Fetches job postings for a given company slug from Lever.
        
        Args:
            target: The company slug (e.g., 'vercel', 'figma')
            
        Returns:
            A list of normalized Job Pydantic models.
        """
        url = f"https://api.lever.co/v0/postings/{target}?mode=json"
        logger.info(f"Fetching Lever jobs from: {url}")
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            try:
                response = await client.get(url)
                if response.status_code == 404:
                    logger.warning(f"Company '{target}' not found on Lever (404).")
                    return []
                response.raise_for_status()
                
                raw_jobs = response.json()
                if not isinstance(raw_jobs, list):
                    logger.warning(f"Lever response for '{target}' is not a list.")
                    return []
                
                company_name = target.replace("-", " ").title()
                
                normalized_jobs = []
                for raw_job in raw_jobs:
                    try:
                        job = self.normalize(raw_job, company_name)
                        normalized_jobs.append(job)
                    except Exception as ex:
                        logger.error(f"Error normalizing Lever job {raw_job.get('id')}: {ex}")
                        
                logger.info(f"Successfully fetched and normalized {len(normalized_jobs)} jobs for {company_name}")
                return normalized_jobs
                
            except httpx.HTTPError as ex:
                logger.error(f"HTTP error fetching Lever jobs for '{target}': {ex}")
                return []
            except Exception as ex:
                logger.error(f"Unexpected error fetching Lever jobs for '{target}': {ex}")
                return []

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        """
        Normalizes raw Lever job representation into a Job model.
        """
        external_id = str(raw.get("id"))
        title = raw.get("text", "").strip()
        
        # Extract location
        categories = raw.get("categories", {})
        location_str = "Unknown"
        if isinstance(categories, dict):
            location_str = categories.get("location", "Unknown").strip()
            
        # Check if remote
        is_remote = False
        title_lower = title.lower()
        loc_lower = location_str.lower()
        
        # Check location or commitment or additional fields for remote indicators
        commitment = categories.get("commitment", "") if isinstance(categories, dict) else ""
        commitment_lower = commitment.lower() if commitment else ""
        
        if "remote" in loc_lower or "remote" in title_lower or "remote" in commitment_lower or "anywhere" in loc_lower:
            is_remote = True
            
        url = raw.get("hostedUrl", f"https://jobs.lever.co/{company}/{external_id}")
        
        # Lever description can contain description + lists of requirements, etc.
        description_parts = []
        
        # Add main description
        desc = raw.get("description", "")
        if desc:
            description_parts.append(clean_html(desc))
            
        # Add lists (requirements, responsibilities, etc.)
        lists = raw.get("lists", [])
        if isinstance(lists, list):
            for lst in lists:
                if isinstance(lst, dict):
                    list_title = lst.get("text", "")
                    list_content = lst.get("content", "")
                    if list_title:
                        description_parts.append(f"\n### {list_title}")
                    if list_content:
                        description_parts.append(clean_html(list_content))
                        
        clean_jd = "\n".join(description_parts).strip()
        
        if not is_remote and clean_jd and ("remote" in clean_jd.lower()[:300] or "work from home" in clean_jd.lower()[:300]):
            is_remote = True

        # Extract posted date (Lever uses createdAt millisecond timestamp)
        posted_at_val = datetime.now()  # local time fallback
        created_at_ms = raw.get("createdAt")
        if created_at_ms is not None:
            try:
                posted_at_val = datetime.utcfromtimestamp(created_at_ms / 1000.0)
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
            scraped_at=datetime.now(),  # local machine time
            posted_at=posted_at_val
        )
