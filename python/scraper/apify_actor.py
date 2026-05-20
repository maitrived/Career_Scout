import os
import logging
from typing import List, Dict, Any
from datetime import datetime
from apify_client import ApifyClient

from python.db.models import Job
from python.scraper.base import BaseScraper
from python.utils.html_parser import clean_html

logger = logging.getLogger(__name__)

class ApifyScraper(BaseScraper):
    """
    Scraper implementation wrapping an Apify Actor.
    Primarily designed to use the actor specified in the SCRAPPER env variable (defaulting to linkedin-jobs-scraper).
    """
    
    def __init__(self):
        self.api_token = os.getenv("APIFY_API_TOKEN")
        self.actor_id = os.getenv("SCRAPPER", "curious_coder/linkedin-jobs-scraper")
        self.client = ApifyClient(self.api_token) if self.api_token else None
        self.source_name = "apify"

    async def fetch_jobs(self, target: str) -> List[Job]:
        """
        Runs the Apify actor with a search URL built from the target.
        
        Args:
            target: Either a full LinkedIn search URL or a search query (e.g. 'Python Scottsdale').
            
        Returns:
            A list of normalized Job Pydantic models.
        """
        if not self.client:
            logger.error("Apify client not initialized. Ensure APIFY_API_TOKEN is set in your .env file.")
            return []

        # If target looks like a URL, use it directly. Otherwise, format it into a LinkedIn search URL.
        if target.startswith("http://") or target.startswith("https://"):
            search_url = target
        else:
            # Construct a public search URL for LinkedIn jobs
            # Using urllib.parse to make it safe
            import urllib.parse
            safe_query = urllib.parse.quote(target)
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={safe_query}"

        logger.info(f"Running Apify actor '{self.actor_id}' for URL: {search_url}")

        run_input = {
            "urls": [search_url],
            "count": 20,              # Sensible default limit per run to manage Apify usage
            "scrapeCompany": False,   # Set to False for faster runs
        }

        try:
            # Run the actor in a separate thread if it is synchronous, but Apify client is blocking by default.
            # Running client call which blocks:
            logger.info("Triggering Apify actor run...")
            run = self.client.actor(self.actor_id).call(run_input=run_input)
            
            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                logger.error("No defaultDatasetId found in Apify run response.")
                return []

            logger.info(f"Apify run finished. Fetching dataset items from {dataset_id}...")
            
            # Fetch dataset items
            items_iterator = self.client.dataset(dataset_id).iterate_items()
            items = list(items_iterator)
            
            logger.info(f"Fetched {len(items)} raw job postings from Apify.")
            
            normalized_jobs = []
            for item in items:
                try:
                    # In some LinkedIn scrapers, companyName might be missing or represented differently.
                    company_name = item.get("companyName", item.get("company", "Unknown Company"))
                    job = self.normalize(item, company_name)
                    normalized_jobs.append(job)
                except Exception as ex:
                    logger.error(f"Error normalizing Apify job item: {ex}")
                    
            return normalized_jobs

        except Exception as ex:
            logger.error(f"Error running Apify scraper for target '{target}': {ex}")
            return []

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        """
        Normalizes raw Apify LinkedIn scraper JSON dictionary to a Job model.
        """
        # Get ID, fallback to link or a hashed version if missing
        external_id = str(raw.get("id", raw.get("jobId", "")))
        if not external_id:
            import hashlib
            link = raw.get("link", raw.get("url", ""))
            external_id = hashlib.md5(link.encode('utf-8')).hexdigest() if link else "unknown_id"

        title = raw.get("title", "Untitled Position").strip()
        location_str = raw.get("location", "Unknown Location").strip()
        
        # Check if remote
        is_remote = False
        title_lower = title.lower()
        loc_lower = location_str.lower()
        
        if "remote" in loc_lower or "remote" in title_lower or "anywhere" in loc_lower:
            is_remote = True

        # Extract Job Description text
        raw_jd = raw.get("description", raw.get("descriptionHtml", raw.get("descriptionText", raw.get("text", ""))))
        clean_jd = clean_html(raw_jd)
        
        if not is_remote and clean_jd and ("remote" in clean_jd.lower()[:300] or "work from home" in clean_jd.lower()[:300]):
            is_remote = True

        url = raw.get("link", raw.get("url", ""))

        # Extract posted date (LinkedIn/Apify scrapers use postedAt, postDate, date, etc.)
        posted_at_val = datetime.utcnow()
        posted_at_str = raw.get("postedAt", raw.get("postDate", raw.get("date", raw.get("timePosted"))))
        if posted_at_str:
            try:
                if len(str(posted_at_str)) == 10:  # e.g. YYYY-MM-DD
                    posted_at_val = datetime.strptime(str(posted_at_str), "%Y-%m-%d")
                else:
                    posted_at_val = datetime.fromisoformat(str(posted_at_str).replace("Z", "+00:00"))
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
