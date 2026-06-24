"""
Generic Playwright scraper for arbitrary job URLs.
"""
import asyncio
import logging
import hashlib
from typing import List, Dict, Any
from playwright.async_api import async_playwright, Browser, Page

from .base import BaseScraper
from python.db.models import Job

logger = logging.getLogger(__name__)

class GenericScraper(BaseScraper):
    source = "generic"

    async def fetch_jobs(self, target: str) -> List[Job]:
        # The 'target' for this scraper will be the actual URL
        logger.info(f"Running Generic Playwright scraper for URL: {target}")
        raw_jobs = []

        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    ignore_https_errors=True
                )
                page: Page = await context.new_page()

                try:
                    await page.goto(target, wait_until="domcontentloaded", timeout=30000)
                    
                    # Try to get plain text of the body
                    raw_jd = await page.evaluate("() => document.body.innerText")
                    
                    # Fallback title if none provided
                    page_title = await page.title()
                    
                    raw_jobs.append({
                        "url": target,
                        "raw_jd": raw_jd.strip() if raw_jd else "",
                        "title": page_title.strip() if page_title else "Imported Job",
                        "company": "Imported Company" # This is a placeholder, should be overridden by excel data
                    })
                    
                except Exception as ex:
                    logger.error(f"Error extracting data from {target}: {ex}")
                finally:
                    await browser.close()
        except Exception as ex:
            logger.error(f"Playwright launch failed for {target}: {ex}")

        # Normalize jobs
        return [self.normalize(r, r.get("company", "Unknown")) for r in raw_jobs]

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        location = raw.get("location", "Remote")
        return Job(
            source=self.source,
            external_id=hashlib.md5(raw.get("url", "").encode()).hexdigest(),
            company=company,
            title=raw.get("title", ""),
            location=location,
            remote="remote" in location.lower(),
            url=raw.get("url", ""),
            raw_jd=raw.get("raw_jd", ""),
        )
