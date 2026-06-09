import httpx
import json
import logging
from typing import List, Dict, Any
from .base import BaseScraper
from python.db.models import Job
from python.config import TARGET_COMPANIES, KEYWORD_FILTERS

logger = logging.getLogger(__name__)

class WorkdayScraper(BaseScraper):
    source = "workday"

    async def fetch_jobs(self, target: str) -> List[Job]:
        # Find the configuration for the target (slug)
        company_info = next((c for c in TARGET_COMPANIES if c.get("slug") == target and c.get("source") == "workday"), None)
        if not company_info:
            logger.error(f"Workday configuration not found for slug '{target}'")
            return []
            
        board = company_info.get("board", "External_Career_Site")
        company_name = company_info.get("name", target.title())
        subdomain = target
        wd = company_info.get("wd", "wd1")  # per-company Workday shard
        
        all_jobs = []
        seen_ids = set()
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                # Create context with a realistic user agent
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    ignore_https_errors=True
                )
                page = await context.new_page()
                
                # Pre-warm the session by visiting the main careers page
                base_url = f"https://{subdomain}.{wd}.myworkdayjobs.com/en-US/{board}"
                try:
                    await page.goto(base_url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(2000) # Give it time to set session cookies
                except Exception as e:
                    logger.warning(f"Error pre-warming workday page for {subdomain}: {e}")
                
                # Now we can query Workday via page.request, which carries the CSRF tokens and cookies
                api_url = f"https://{subdomain}.{wd}.myworkdayjobs.com/wday/cxs/{subdomain}/{board}/jobs"
                for keyword in KEYWORD_FILTERS:
                    offset = 0
                    limit = 20
                    consecutive_empty_pages = 0
                    
                    while True:
                        payload = {
                            "appliedFacets": {},
                            "limit": limit,
                            "offset": offset,
                            "searchText": keyword
                        }
                        
                        try:
                            r = await page.request.post(
                                api_url,
                                data=json.dumps(payload),
                                headers={"Accept": "application/json", "Content-Type": "application/json"}
                            )
                            if not r.ok:
                                text = await r.text()
                                logger.warning(f"Workday API returned {r.status} for {subdomain}: {text}")
                                break
                                
                            data = await r.json()
                            jobs_raw = data.get("jobPostings", [])
                            total_from_api = data.get("total", 0)
                            
                            if offset == 0:
                                logger.info(f"Workday API reports {total_from_api} total jobs for '{keyword}' at {company_name}")
                                
                            if not jobs_raw:
                                break
                                
                            page_kept = 0
                            for raw in jobs_raw:
                                ext_path = raw.get("externalPath", "")
                                if not ext_path or ext_path in seen_ids:
                                    continue
                                    
                                seen_ids.add(ext_path)
                                page_kept += 1
                                
                                # Fetch job details (raw_jd)
                                detail_url = f"https://{subdomain}.{wd}.myworkdayjobs.com/wday/cxs/{subdomain}/{board}{ext_path}"
                                try:
                                    detail_r = await page.request.get(detail_url, headers={"Accept": "application/json"})
                                    if detail_r.ok:
                                        detail_data = await detail_r.json()
                                        raw["jobDescription"] = detail_data.get("jobPostingInfo", {}).get("jobDescription", "")
                                    else:
                                        raw["jobDescription"] = ""
                                except Exception as ex:
                                    logger.error(f"Error fetching detail for {ext_path}: {ex}")
                                    raw["jobDescription"] = ""
                                    
                                # Inject config variables for normalize()
                                raw["_subdomain"] = subdomain
                                raw["_board"] = board
                                raw["_wd"] = wd
                                
                                job_model = self.normalize(raw, company_name)
                                all_jobs.append(job_model)
                                
                            logger.info(f"  [{keyword}] Page offset={offset}: {len(jobs_raw)} returned, {page_kept} kept (total unique: {len(all_jobs)})")
                            
                            if page_kept == 0:
                                consecutive_empty_pages += 1
                            else:
                                consecutive_empty_pages = 0
                                
                            offset += limit
                            
                            if offset >= total_from_api:
                                break
                                
                            if consecutive_empty_pages >= 3:
                                logger.info(f"  [{keyword}] 3 consecutive empty pages — skipping remaining results")
                                break
                                
                        except Exception as ex:
                            logger.error(f"Error fetching workday jobs for {subdomain} with keyword '{keyword}' at offset {offset}: {ex}")
                            break
                        
                await browser.close()
                
        except Exception as e:
            logger.error(f"Failed to launch playwright for Workday scraper: {e}")
            
        return all_jobs

    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        ext_path = raw.get("externalPath", "")
        subdomain = raw.get("_subdomain", company.lower().replace(" ", ""))
        board = raw.get("_board", "External_Career_Site")
        wd = raw.get("_wd", "wd1")
        
        # Workday UI URL
        url = f"https://{subdomain}.{wd}.myworkdayjobs.com/en-US/{board}{ext_path}"
        
        location = raw.get("locationsText", "")
        
        return Job(
            source=self.source,
            external_id=ext_path,  # externalPath is unique
            company=company,
            title=raw.get("title", ""),
            location=location,
            remote="remote" in location.lower(),
            url=url,
            raw_jd=raw.get("jobDescription", "")
        )
