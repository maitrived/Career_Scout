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
    """Scrapes Supabase via the Ashby API — returns jobs with full JDs in one call."""
    import httpx
    import re
    jobs = []
    try:
        async with httpx.AsyncClient(verify=False, timeout=20) as client:
            r = await client.get("https://api.ashbyhq.com/posting-api/job-board/supabase")
            if r.status_code == 200:
                data = r.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    job_url = item.get("applyUrl", item.get("jobUrl", ""))
                    location = item.get("location", "Remote")
                    # descriptionPlain is the clean plain-text JD — no HTML parsing needed
                    raw_jd = item.get("descriptionPlain", "") or ""
                    # Strip excess whitespace
                    raw_jd = re.sub(r'\n{3,}', '\n\n', raw_jd).strip()
                    if title and job_url:
                        jobs.append({
                            "title": title,
                            "url": job_url,
                            "location": location,
                            "external_id": item.get("id", hashlib.md5(job_url.encode()).hexdigest()),
                            "company": "Supabase",
                            "raw_jd": raw_jd[:8000],
                        })
                logger.info(f"Supabase Ashby API returned {len(jobs)} jobs")
                return jobs
    except Exception as e:
        logger.error(f"Failed to fetch Supabase jobs via Ashby API: {e}")

    # Fallback: Playwright scrape of the careers page (no JD available this way)
    logger.warning("Falling back to Playwright for Supabase — JDs will be empty")
    await page.goto("https://supabase.com/careers", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)
    jobs = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('a[href*="ashbyhq.com/supabase/"]').forEach(el => {
                const href = el.href;
                const title = el.querySelector('h3, h2, [class*="title"]')?.textContent?.trim()
                           || el.textContent?.trim();
                const location = el.querySelector('[class*="location"]')?.textContent?.trim() || 'Remote';
                if (title && href) results.push({ title, url: href, location });
            });
            return results;
        }
    """)
    return [{"title": j["title"], "url": j["url"], "location": j["location"],
             "external_id": hashlib.md5(j["url"].encode()).hexdigest(),
             "company": "Supabase", "raw_jd": ""} for j in jobs if j.get("title")]


async def extract_stripe(page: Page) -> List[Dict[str, Any]]:
    """Scrapes Stripe via Playwright (JS-rendered) then fetches JDs from detail pages."""
    import httpx
    import re
    jobs = []

    # Step 1: Get job listings via Playwright (the search page is JS-rendered)
    try:
        await page.goto("https://stripe.com/jobs/search", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        raw_listings = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('a[href*="/jobs/listing/"]').forEach(el => {
                    const href = el.href;
                    const title = el.querySelector('[class*="JobCard__title"], h3, h2')?.textContent?.trim()
                               || el.textContent?.trim();
                    const location = el.querySelector('[class*="location"], [class*="Location"]')?.textContent?.trim() || '';
                    if (title && href) results.push({ title, url: href, location });
                });
                return results;
            }
        """)
        logger.info(f"Stripe Playwright found {len(raw_listings)} job listings")
    except Exception as e:
        logger.error(f"Stripe Playwright listing scrape failed: {e}")
        raw_listings = []

    if not raw_listings:
        return []

    # Step 2: Fetch JD from each detail page via httpx
    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        for item in raw_listings:
            url = item.get("url", "")
            raw_jd = ""
            if url:
                try:
                    r = await client.get(url, headers={"Accept": "text/html"})
                    if r.status_code == 200:
                        # Extract visible text from the job description section
                        # Stripe uses JSON-LD or structured data — try to grab plain text
                        html = r.text
                        # Pull text between common JD markers
                        import re as _re
                        # Remove script/style tags
                        html_clean = _re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html, flags=_re.S)
                        # Strip all HTML tags
                        text = _re.sub(r'<[^>]+>', ' ', html_clean)
                        # Collapse whitespace
                        text = _re.sub(r'[ \t]+', ' ', text)
                        text = _re.sub(r'\n{3,}', '\n\n', text).strip()
                        raw_jd = text[:8000]
                except Exception as ex:
                    logger.debug(f"Could not fetch Stripe JD for {url}: {ex}")

            jobs.append({
                "title": item["title"],
                "url": url,
                "location": item.get("location", ""),
                "external_id": hashlib.md5(url.encode()).hexdigest(),
                "company": "Stripe",
                "raw_jd": raw_jd,
            })

    logger.info(f"Stripe: fetched JDs for {sum(1 for j in jobs if j['raw_jd'])} / {len(jobs)} jobs")
    return jobs


async def extract_rippling(page: Page) -> List[Dict[str, Any]]:
    """Scrapes Rippling via HTTP API instead of Playwright"""
    import httpx
    jobs = []
    try:
        async with httpx.AsyncClient(verify=False) as client:
            # We don't have the exact JSON endpoint but we will try the one provided by the user
            r = await client.get(
                "https://ats.rippling.com/api/ats/v1/jobs",
                params={"limit": 50, "offset": 0},
                headers={"Accept": "application/json"}
            )
            if r.status_code == 200:
                data = r.json()
                for item in data: # Assume list of jobs or data.get('jobs')
                    if isinstance(item, dict):
                        title = item.get("name") or item.get("title")
                        url = item.get("url")
                        location = item.get("location")
                        if title and url:
                            jobs.append({
                                "title": title,
                                "url": url,
                                "location": location or "",
                                "external_id": hashlib.md5(url.encode()).hexdigest(),
                                "company": "Rippling",
                                "raw_jd": ""
                            })
                if jobs:
                    return jobs
    except Exception as e:
        logger.error(f"Failed to fetch Rippling jobs via JSON API: {e}")
        
    # Fallback to Playwright
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
                               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    ignore_https_errors=True
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
