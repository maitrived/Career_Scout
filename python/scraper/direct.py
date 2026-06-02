"""
Direct career page scraper using Playwright.
Used for companies that:
  1. Have a proprietary career portal (no public ATS API)
  2. Use JavaScript-heavy pages that require a real browser

Each company has a custom extractor function that knows how to parse
their specific career page structure.
"""
import asyncio
import logging
import hashlib
from typing import List, Dict, Any, Callable, Awaitable
from playwright.async_api import async_playwright, Page, Browser

from .base import BaseScraper
from python.db.models import Job
from python.config import TARGET_COMPANIES

logger = logging.getLogger(__name__)

# Type alias for extractor functions
Extractor = Callable[[Page], Awaitable[List[Dict[str, Any]]]]


# ─── Extractor Functions ──────────────────────────────────────────────────────

async def extract_notion(page: Page) -> List[Dict[str, Any]]:
    """Scrapes https://www.notion.so/careers"""
    await page.goto("https://www.notion.so/careers", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)

    jobs = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('a[href*="/careers/"]').forEach(el => {
                const href = el.href;
                const title = el.querySelector('h3, h2, [class*="title"], [class*="role"]')?.textContent?.trim()
                           || el.textContent?.trim();
                const location = el.querySelector('[class*="location"]')?.textContent?.trim() || 'Remote';
                if (title && href && href.includes('/careers/') && !href.endsWith('/careers/')) {
                    results.push({ title, url: href, location });
                }
            });
            return results;
        }
    """)
    return [{"title": j["title"], "url": j["url"], "location": j["location"],
             "external_id": hashlib.md5(j["url"].encode()).hexdigest(),
             "company": "Notion", "raw_jd": ""} for j in jobs if j.get("title")]


async def extract_supabase(page: Page) -> List[Dict[str, Any]]:
    """Scrapes https://supabase.com/careers"""
    await page.goto("https://supabase.com/careers", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)

    jobs = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('a[href*="/careers/"]').forEach(el => {
                const href = el.href;
                const title = el.querySelector('h3, h2, [class*="title"]')?.textContent?.trim()
                           || el.textContent?.trim();
                const location = el.querySelector('[class*="location"]')?.textContent?.trim() || 'Remote';
                if (title && href && href.includes('/careers/') && !href.endsWith('/careers/')) {
                    results.push({ title, url: href, location });
                }
            });
            return results;
        }
    """)
    return [{"title": j["title"], "url": j["url"], "location": j["location"],
             "external_id": hashlib.md5(j["url"].encode()).hexdigest(),
             "company": "Supabase", "raw_jd": ""} for j in jobs if j.get("title")]


async def extract_stripe(page: Page) -> List[Dict[str, Any]]:
    """Scrapes https://stripe.com/jobs"""
    await page.goto("https://stripe.com/jobs/search", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)

    jobs = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('a[href*="/jobs/listing/"]').forEach(el => {
                const href = el.href;
                const title = el.querySelector('[class*="JobCard__title"], h3, h2')?.textContent?.trim()
                           || el.textContent?.trim();
                const location = el.querySelector('[class*="location"], [class*="Location"]')?.textContent?.trim() || '';
                if (title && href) {
                    results.push({ title, url: href, location });
                }
            });
            return results;
        }
    """)
    return [{"title": j["title"], "url": j["url"], "location": j["location"],
             "external_id": hashlib.md5(j["url"].encode()).hexdigest(),
             "company": "Stripe", "raw_jd": ""} for j in jobs if j.get("title")]


async def extract_rippling(page: Page) -> List[Dict[str, Any]]:
    """Scrapes https://ats.rippling.com/rippling/jobs"""
    await page.goto("https://ats.rippling.com/rippling/jobs", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)

    jobs = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('a[href*="/jobs/"]').forEach(el => {
                const href = el.href;
                const title = el.querySelector('h2, h3, [class*="title"]')?.textContent?.trim()
                           || el.textContent?.trim();
                const location = el.querySelector('[class*="location"]')?.textContent?.trim() || '';
                if (title && href && !href.endsWith('/jobs/')) {
                    results.push({ title, url: href, location });
                }
            });
            return results;
        }
    """)
    return [{"title": j["title"], "url": j["url"], "location": j["location"],
             "external_id": hashlib.md5(j["url"].encode()).hexdigest(),
             "company": "Rippling", "raw_jd": ""} for j in jobs if j.get("title")]


# ─── Registry: slug → (url, extractor) ───────────────────────────────────────

DIRECT_SCRAPERS: Dict[str, Extractor] = {
    "notion":    extract_notion,
    "supabase":  extract_supabase,
    "stripe":    extract_stripe,
    "rippling":  extract_rippling,
}


# ─── Main Scraper Class ───────────────────────────────────────────────────────

class DirectScraper(BaseScraper):
    source = "direct"

    async def fetch_jobs(self, target: str) -> List[Job]:
        extractor = DIRECT_SCRAPERS.get(target)
        if not extractor:
            logger.warning(f"No direct scraper registered for '{target}'")
            return []

        company_info = next(
            (c for c in TARGET_COMPANIES if c.get("slug") == target and c.get("source") == "direct"),
            None
        )
        company_name = company_info.get("name", target.title()) if company_info else target.title()

        logger.info(f"Running Playwright direct scraper for {company_name}...")
        raw_jobs = []

        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                try:
                    raw_jobs = await extractor(page)
                    logger.info(f"Direct scraper found {len(raw_jobs)} jobs for {company_name}")
                except Exception as ex:
                    logger.error(f"Error in direct scraper for {target}: {ex}")
                finally:
                    await browser.close()
        except Exception as ex:
            logger.error(f"Playwright launch failed for {target}: {ex}")

        return [self.normalize(r, company_name) for r in raw_jobs if r.get("title")]

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        location = raw.get("location", "")
        return Job(
            source=self.source,
            external_id=raw.get("external_id", hashlib.md5(raw.get("url", "").encode()).hexdigest()),
            company=raw.get("company", company),
            title=raw.get("title", ""),
            location=location,
            remote="remote" in location.lower() or not location,
            url=raw.get("url", ""),
            raw_jd=raw.get("raw_jd", ""),
        )
