import os
import logging
import hashlib
from typing import List, Dict, Any
from datetime import datetime
from apify_client import ApifyClient

from python.db.models import Job
from python.scraper.base import BaseScraper
from python.utils.html_parser import clean_html

logger = logging.getLogger(__name__)

class ApifyScraper(BaseScraper):
    def __init__(self):
        self.api_token = os.getenv("APIFY_API_TOKEN")
        self.client = ApifyClient(self.api_token) if self.api_token else None

    async def fetch_jobs(self, target: str) -> List[Job]:
        # Fallback for old pipeline calls
        actor_id = os.getenv("SCRAPPER", "curious_coder/linkedin-jobs-scraper")
        
        if target.startswith("http://") or target.startswith("https://"):
            search_url = target
        else:
            import urllib.parse
            safe_query = urllib.parse.quote(target)
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={safe_query}"

        run_input = {
            "urls": [search_url],
            "count": 20,
            "scrapeCompany": False,
        }
        
        raw_jobs = await self.run_actor(actor_id, run_input)
        return [self.normalize(raw, raw.get("companyName", raw.get("company", "Unknown Company"))) for raw in raw_jobs]

    async def run_actor(self, actor_id: str, run_input: dict) -> List[dict]:
        if not self.client:
            logger.error("Apify client not initialized. Ensure APIFY_API_TOKEN is set in your .env file.")
            return []

        logger.info(f"Triggering Apify actor run for {actor_id}...")
        try:
            run = self.client.actor(actor_id).call(run_input=run_input)
            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                logger.error("No defaultDatasetId found in Apify run response.")
                return []

            logger.info(f"Apify run finished. Fetching dataset items from {dataset_id}...")
            items_iterator = self.client.dataset(dataset_id).iterate_items()
            items = list(items_iterator)
            logger.info(f"Fetched {len(items)} raw items from Apify actor {actor_id}.")
            return items
        except Exception as ex:
            logger.error(f"Error running Apify scraper actor '{actor_id}': {ex}")
            return []

    # specific normalizers
    def normalize_linkedin(self, raw: Dict[str, Any]) -> Job:
        company = raw.get("companyName", raw.get("company", "Unknown Company"))
        return self.normalize(raw, company)
        
    def normalize_yc(self, raw: Dict[str, Any]) -> Job:
        company = raw.get("companyName", raw.get("company", "Unknown Company"))
        title = raw.get("title", raw.get("jobRole", raw.get("role", "Untitled Position")))
        location = raw.get("location", "Remote")
        url = raw.get("url", raw.get("jobUrl", ""))
        external_id = str(raw.get("jobId", raw.get("id", "")))
        if not external_id:
            external_id = hashlib.md5(url.encode('utf-8')).hexdigest() if url else "unknown_yc_id"
        raw_jd = clean_html(raw.get("descriptionHtml", raw.get("description", "")))
        
        return Job(
            source="yc",
            external_id=external_id,
            company=company,
            title=title,
            location=location,
            remote=True, # YC jobs we scrape are set to remote via config
            url=url,
            raw_jd=raw_jd,
            scraped_at=datetime.utcnow()
        )

    def normalize_wellfound(self, raw: Dict[str, Any]) -> Job:
        company = raw.get("company", raw.get("companyName", raw.get("startup", "Unknown Company")))
        title = raw.get("title", "Untitled Position")
        location = raw.get("location", "Remote")
        url = raw.get("applyUrl", raw.get("jobUrl", raw.get("url", "")))
        
        # ID generation
        raw_id = raw.get("id", "")
        external_id = str(raw_id) if raw_id else hashlib.md5(url.encode('utf-8')).hexdigest() if url else "unknown_wf_id"
        
        # Remote detection
        remote_val = raw.get("remote", "")
        is_remote = True if str(remote_val).lower() == "yes" else False
        if "remote" in location.lower():
            is_remote = True

        raw_jd = raw.get("description_html", raw.get("description_text", raw.get("description", "")))
        clean_jd = clean_html(raw_jd)
        
        return Job(
            source="wellfound",
            external_id=external_id,
            company=company,
            title=title,
            location=location,
            remote=is_remote,
            url=url,
            raw_jd=clean_jd,
            scraped_at=datetime.utcnow()
        )

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        external_id = str(raw.get("id", raw.get("jobId", "")))
        if not external_id:
            link = raw.get("link", raw.get("url", ""))
            external_id = hashlib.md5(link.encode('utf-8')).hexdigest() if link else "unknown_id"

        title = raw.get("title", "Untitled Position").strip()
        location_str = raw.get("location", "Unknown Location").strip()
        
        is_remote = False
        title_lower = title.lower()
        loc_lower = location_str.lower()
        
        if "remote" in loc_lower or "remote" in title_lower or "anywhere" in loc_lower:
            is_remote = True

        raw_jd = raw.get("description", raw.get("descriptionHtml", raw.get("descriptionText", raw.get("text", ""))))
        clean_jd = clean_html(raw_jd)
        
        if not is_remote and clean_jd and ("remote" in clean_jd.lower()[:300] or "work from home" in clean_jd.lower()[:300]):
            is_remote = True

        url = raw.get("link", raw.get("url", ""))

        posted_at_val = datetime.utcnow()
        posted_at_str = raw.get("postedAt", raw.get("postDate", raw.get("date", raw.get("timePosted"))))
        if posted_at_str:
            try:
                if len(str(posted_at_str)) == 10:
                    posted_at_val = datetime.strptime(str(posted_at_str), "%Y-%m-%d")
                else:
                    posted_at_val = datetime.fromisoformat(str(posted_at_str).replace("Z", "+00:00"))
            except Exception:
                pass

        return Job(
            source="apify_linkedin",
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

class YcScraper(ApifyScraper):
    source = "yc"
    async def fetch_jobs(self, target: str = "") -> List[Job]:
        from python.config import YC_ACTOR, YC_CONFIG
        logger.info("Running YC jobs scraper via Apify...")
        raw_jobs = await self.run_actor(YC_ACTOR, YC_CONFIG)
        return [self.normalize_yc(raw) for raw in raw_jobs]

class WellfoundScraper(ApifyScraper):
    source = "wellfound"
    async def fetch_jobs(self, target: str = "") -> List[Job]:
        from python.config import WELLFOUND_ACTOR, WELLFOUND_CONFIG
        logger.info("Running Wellfound jobs scraper via Apify...")
        raw_jobs = await self.run_actor(WELLFOUND_ACTOR, WELLFOUND_CONFIG)
        return [self.normalize_wellfound(raw) for raw in raw_jobs]
