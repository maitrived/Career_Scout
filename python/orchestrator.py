import logging
import asyncio
from typing import Optional, Dict, Any, List

from python.config import TARGET_COMPANIES
from python.db.client import (
    save_job, get_pipeline_status, get_unscored_jobs, get_job, 
    save_score, save_resume_version, save_application, get_application_by_job
)
from python.scraper.greenhouse import GreenhouseScraper
from python.scraper.lever import LeverScraper
from python.scraper.ashby import AshbyScraper
from python.scraper.apify_actor import ApifyScraper
from python.db.models import Job, Score, ResumeVersion, Application
from python.scorer.evaluator import JobEvaluator
from python.tailor import ResumeTailor, CoverLetterGenerator

logger = logging.getLogger(__name__)

async def run_scraper_for_company(company_info: dict) -> List[Job]:
    """Runs the appropriate scraper for a single company configuration dict."""
    name = company_info.get("name", "Unknown")
    slug = company_info.get("slug")
    source = company_info.get("source", "").lower()
    
    logger.info(f"Running scraper for {name} ({slug}) using {source}...")
    
    if source == "greenhouse":
        scraper = GreenhouseScraper()
    elif source == "lever":
        scraper = LeverScraper()
    elif source == "ashby":
        scraper = AshbyScraper()
    elif source == "workday":
        from python.scraper.workday import WorkdayScraper
        scraper = WorkdayScraper()
    elif source == "smartrecruiters":
        from python.scraper.smartrecruiters import SmartRecruitersScraper
        scraper = SmartRecruitersScraper()
    elif source == "jobvite":
        from python.scraper.jobvite import JobviteScraper
        scraper = JobviteScraper()
    elif source == "direct":
        from python.scraper.direct import DirectScraper
        scraper = DirectScraper()
    elif source == "yc":
        from python.scraper.apify_actor import YcScraper
        scraper = YcScraper()
    elif source == "wellfound":
        from python.scraper.apify_actor import WellfoundScraper
        scraper = WellfoundScraper()
    else:
        logger.warning(f"Unknown scraper source '{source}' for company '{name}'. Skipping.")
        return []
        
    return await scraper.fetch_jobs(slug)

async def scrape_pipeline(company_slug: Optional[str] = None, search_query: Optional[str] = None, source: Optional[str] = None, run_all: bool = False) -> Dict[str, Any]:
    """
    Orchestrates the scraping stage of the pipeline.
    
    Args:
        company_slug: Optional specific company slug to scrape (e.g. 'retool').
        search_query: Optional search query to pass to the Apify/LinkedIn scraper.
        
    Returns:
        A dictionary containing run metrics (jobs scraped, jobs saved, etc.)
    """
    total_scraped = 0
    saved_count = 0
    
    # Track results by company
    metrics = {
        "companies_attempted": 0,
        "companies_successful": 0,
        "jobs_scraped": 0,
        "jobs_saved": 0,
        "errors": [],
        "zero_job_companies": []
    }
    
    from python.utils.job_filter import passes_job_filter

    # Scenario 1: Apify / LinkedIn search query was explicitly requested
    if search_query:
        logger.info(f"Initiating LinkedIn/Apify scrape for query: '{search_query}'")
        apify_scraper = ApifyScraper()
        jobs = await apify_scraper.fetch_jobs(search_query)
        metrics["companies_attempted"] = 1
        metrics["jobs_scraped"] = len(jobs)
        
        for job in jobs:
            if not passes_job_filter(job):
                continue
            try:
                save_job(job)
                saved_count += 1
            except Exception as ex:
                logger.error(f"Error saving LinkedIn job: {ex}")
                metrics["errors"].append(str(ex))
                
        metrics["jobs_saved"] = saved_count
        metrics["companies_successful"] = 1 if saved_count > 0 else 0
        return metrics

    # Scenario 2: Specific Greenhouse/Lever/Ashby company slug was requested
    if company_slug:
        # Find matching company config in TARGET_COMPANIES
        company_configs = [c for c in TARGET_COMPANIES if c["slug"].lower() == company_slug.lower()]
        
        if not company_configs:
            # Fallback: if not in list, try running it across all three standard board scrapers
            logger.info(f"Company slug '{company_slug}' not found in configuration list. Attempting fallback discovery...")
            company_configs = [
                {"name": company_slug.title(), "slug": company_slug, "source": "greenhouse"},
                {"name": company_slug.title(), "slug": company_slug, "source": "lever"},
                {"name": company_slug.title(), "slug": company_slug, "source": "ashby"},
                {"name": company_slug.title(), "slug": company_slug, "source": "workday"},
                {"name": company_slug.title(), "slug": company_slug, "source": "smartrecruiters"},
                {"name": company_slug.title(), "slug": company_slug, "source": "jobvite"},
                {"name": company_slug.title(), "slug": company_slug, "source": "direct"}
            ]
            
        metrics["companies_attempted"] = len(company_configs)
        
        for config in company_configs:
            try:
                jobs = await run_scraper_for_company(config)
                if jobs:
                    metrics["companies_successful"] += 1
                    total_scraped += len(jobs)
                    
                    for job in jobs:
                        if not passes_job_filter(job):
                            continue
                        try:
                            save_job(job)
                            saved_count += 1
                        except Exception as ex:
                            logger.error(f"Error saving job: {ex}")
                            metrics["errors"].append(str(ex))
            except Exception as ex:
                logger.error(f"Failed executing scraper for {config.get('name')}: {ex}")
                metrics["errors"].append(str(ex))
                
        metrics["jobs_scraped"] = total_scraped
        metrics["jobs_saved"] = saved_count
        return metrics

    # Scenario 3: A specific source was requested without a company/query (e.g., --source yc)
    if source and not company_slug and not search_query:
        logger.info(f"Scraping all companies for source: {source}...")
        
        if source in ["yc", "wellfound"]:
            # These are aggregator scrapers, not per-company
            config = {"name": source.title(), "slug": source, "source": source}
            metrics["companies_attempted"] = 1
            jobs = await run_scraper_for_company(config)
            
            if jobs:
                metrics["companies_successful"] = 1
                total_scraped = len(jobs)
                for job in jobs:
                    if passes_job_filter(job):
                        try:
                            save_job(job)
                            saved_count += 1
                        except Exception as ex:
                            logger.error(f"Error saving {source} job: {ex}")
                            metrics["errors"].append(str(ex))
            metrics["jobs_scraped"] = total_scraped
            metrics["jobs_saved"] = saved_count
            return metrics
            
        # For standard sources, filter TARGET_COMPANIES by source
        targets = [c for c in TARGET_COMPANIES if c.get("source") == source]
        metrics["companies_attempted"] = len(targets)
        for config in targets:
            try:
                jobs = await run_scraper_for_company(config)
                if jobs:
                    metrics["companies_successful"] += 1
                    total_scraped += len(jobs)
                    for job in jobs:
                        if not passes_job_filter(job):
                            continue
                        try:
                            save_job(job)
                            saved_count += 1
                        except Exception as ex:
                            logger.error(f"Error saving job: {ex}")
                            metrics["errors"].append(str(ex))
                else:
                    metrics["zero_job_companies"].append(config.get('name'))
            except Exception as ex:
                logger.error(f"Failed executing scraper for {config.get('name')}: {ex}")
                metrics["errors"].append(str(ex))
                
        metrics["jobs_scraped"] = total_scraped
        metrics["jobs_saved"] = saved_count
        return metrics

    # Scenario 4: No company or search query specified; run all TARGET_COMPANIES scrapers
    logger.info("Scraping all configured target companies...")
    metrics["companies_attempted"] = len(TARGET_COMPANIES)
    
    # If --all is passed, we also want to explicitly run the YC and Wellfound aggregators
    targets_to_run = list(TARGET_COMPANIES)
    if run_all:
        logger.info("Run All enabled: appending YC and Wellfound to target list.")
        targets_to_run.append({"name": "Y Combinator", "slug": "yc", "source": "yc"})
        targets_to_run.append({"name": "Wellfound", "slug": "wellfound", "source": "wellfound"})
        metrics["companies_attempted"] += 2
        
    for config in targets_to_run:
        try:
            jobs = await run_scraper_for_company(config)
            if jobs:
                metrics["companies_successful"] += 1
                total_scraped += len(jobs)
                
                for job in jobs:
                    if not passes_job_filter(job):
                        continue
                    try:
                        save_job(job)
                        saved_count += 1
                    except Exception as ex:
                        logger.error(f"Error saving job: {ex}")
                        metrics["errors"].append(str(ex))
            else:
                metrics["zero_job_companies"].append(config.get('name'))
        except Exception as ex:
            logger.error(f"Failed executing scraper for {config.get('name')}: {ex}")
            metrics["errors"].append(str(ex))
            
    metrics["jobs_scraped"] = total_scraped
    metrics["jobs_saved"] = saved_count
    return metrics

async def score_pipeline(
    job_id: Optional[str] = None, 
    within_days: Optional[int] = None, 
    company_slug: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Orchestrates the scoring stage. Evaluates jobs against Parva's profile and saves fit scores.
    """
    metrics = {
        "jobs_evaluated": 0,
        "jobs_advanced": 0,
        "jobs_skipped": 0,
        "details": [],
        "dry_run": dry_run
    }
    
    # 1. Fetch target jobs
    target_jobs = []
    if job_id:
        single_job = get_job(job_id)
        if single_job:
            target_jobs = [single_job]
        else:
            logger.error(f"Job with ID '{job_id}' not found in database.")
            return metrics
    else:
        target_jobs = get_unscored_jobs(within_days=within_days, company_slug=company_slug)
        
    if not target_jobs:
        logger.info("No unscored jobs found matching evaluation criteria.")
        return metrics
        
    logger.info(f"Loaded {len(target_jobs)} jobs for scoring evaluation.")
    
    if dry_run:
        logger.info("[DRY RUN] Skipping API execution and database writes.")
        for job in target_jobs:
            metrics["details"].append({
                "id": str(job.id),
                "company": job.company,
                "title": job.title,
                "posted_at": job.posted_at.isoformat() if job.posted_at else "Unknown"
            })
        metrics["jobs_evaluated"] = len(target_jobs)
        return metrics
        
    # 2. Perform LLM scoring evaluations
    evaluator = JobEvaluator()
    for job in target_jobs:
        logger.info(f"Scoring job: '{job.title}' at {job.company}...")
        try:
            # Call evaluator
            score = evaluator.evaluate_job(job)
            save_score(score)
            
            advanced = score.overall_score >= 3.5
            if advanced:
                metrics["jobs_advanced"] += 1
            else:
                metrics["jobs_skipped"] += 1
                
            metrics["jobs_evaluated"] += 1
            metrics["details"].append({
                "id": str(job.id),
                "company": job.company,
                "title": job.title,
                "score": score.overall_score,
                "advanced": advanced,
                "rationale": score.rationale,
                "red_flags": score.red_flags
            })
        except Exception as ex:
            logger.error(f"Error scoring job {job.id}: {ex}")
            
        # Rate limit mitigation for NIM (40 req/min)
        await asyncio.sleep(1.5)
            
    return metrics

async def tailor_pipeline(job_id: str) -> Dict[str, Any]:
    """
    Orchestrates the tailoring stage. Generates a tailored resume (JSON/Markdown) 
    and cover letter (plain-text) for a job and saves them to the DB.
    """
    metrics = {
        "success": False,
        "job_id": job_id,
        "company": "",
        "title": "",
        "error": None
    }
    
    # 1. Fetch the job details
    job = get_job(job_id)
    if not job:
        metrics["error"] = f"Job ID {job_id} not found."
        logger.error(metrics["error"])
        return metrics
        
    metrics["company"] = job.company
    metrics["title"] = job.title
    
    logger.info(f"Generating tailored materials for '{job.title}' at {job.company}...")
    
    try:
        # 2. Instantiate tailor tools
        tailor_tool = ResumeTailor()
        cl_gen = CoverLetterGenerator()
        
        # 3. Generate tailored content using Gemini
        tailored_json = tailor_tool.tailor(job)
        tailored_md = tailor_tool.to_markdown(tailored_json)
        cover_letter = cl_gen.generate(job)
        
        # 4. Save tailored ResumeVersion to DB
        rv = ResumeVersion(
            job_id=job.id,
            resume_md=tailored_md,
            cover_letter=cover_letter
        )
        saved_rv = save_resume_version(rv)
        
        # 5. Check if an application tracking record already exists, or create/update it
        app = get_application_by_job(job.id)
        if app:
            app.resume_version_id = saved_rv.id
            app.status = "ready"
            app.updated_at = None  # will auto-generate in save_application
            save_application(app)
        else:
            new_app = Application(
                job_id=job.id,
                resume_version_id=saved_rv.id,
                status="ready"
            )
            save_application(new_app)
            
        metrics["success"] = True
        logger.info(f"[SUCCESS] Tailored resume & cover letter saved for {job.company}!")
        return metrics
        
    except Exception as ex:
        metrics["error"] = str(ex)
        logger.error(f"Tailoring failed: {ex}")
        return metrics

async def package_pipeline(job_id: str) -> Dict[str, Any]:
    """
    Orchestrates the packaging stage. Reads tailored resume markdown from the DB,
    converts it to a PDF using the TS Microservice, and saves the file path to the DB.
    Also generates a cover letter PDF from the stored cover letter text.
    """
    from python.utils.pdf_bridge import generate_pdf, generate_cover_letter_pdf
    
    metrics = {
        "success": False,
        "job_id": job_id,
        "pdf_path": None,
        "cover_letter_pdf_path": None,
        "page_fill": 0,
        "initial_fill": 0,
        "error": None
    }
    
    try:
        app = get_application_by_job(job_id)
        if not app or not app.resume_version_id:
            raise ValueError(f"No tailored application/resume version found for job ID {job_id}. Please run the tailor command first.")
            
        # Fetch the resume version directly
        import sqlite3
        from python.db.client import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, job_id, resume_md, cover_letter, pdf_path, created_at FROM resume_versions WHERE id = ?", (str(app.resume_version_id),))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise ValueError(f"ResumeVersion ID {app.resume_version_id} not found in database.")
            
        resume_md = row['resume_md']
        cover_letter_text = row['cover_letter']
        logger.info(f"Generating PDF package for job '{job_id}'...")
        
        # ── 1. Resume PDF ────────────────────────────────────────────────────
        pdf_path, page_fill, initial_fill = await generate_pdf(resume_md, job_id)
        
        # ── 2. Cover Letter PDF ──────────────────────────────────────────────
        cover_letter_pdf_path = None
        if cover_letter_text and cover_letter_text.strip():
            try:
                cover_letter_pdf_path = await generate_cover_letter_pdf(cover_letter_text, job_id)
                logger.info(f"Cover letter PDF generated: {cover_letter_pdf_path}")
            except Exception as cl_ex:
                logger.warning(f"Cover letter PDF generation failed (non-fatal): {cl_ex}")
        else:
            logger.warning("No cover letter text found in DB — skipping cover letter PDF.")
        
        # Determine page_fill value to store based on conditions
        stored_page_fill = page_fill if 95 <= page_fill <= 100 else initial_fill

        # ── 3. Persist pdf_path back to ResumeVersion ────────────────────────
        rv = ResumeVersion(
            id=app.resume_version_id,
            job_id=row['job_id'],
            resume_md=row['resume_md'],
            cover_letter=row['cover_letter'],
            pdf_path=pdf_path,
            cover_letter_pdf_path=cover_letter_pdf_path,
            page_fill=stored_page_fill,
            created_at=row['created_at']
        )
        save_resume_version(rv)
        
        metrics["success"] = True
        metrics["pdf_path"] = pdf_path
        metrics["cover_letter_pdf_path"] = cover_letter_pdf_path
        metrics["page_fill"] = page_fill
        metrics["initial_fill"] = initial_fill
        
        if page_fill < 88:
            logger.warning(f"⚠️ PDF content underfilled: Only {page_fill}% of the A4 page is utilized. Consider expanding experience/summary.")
        elif page_fill > 100:
            logger.warning(f"⚠️ PDF content overflowed: Page fill is {page_fill}%. It may span to a second page.")
        else:
            logger.info(f"✓ PDF layout fill is optimal: {page_fill}% page fit.")
            
        logger.info(f"[SUCCESS] PDF Package Generated: {pdf_path} ({page_fill}% page fill)")
        if cover_letter_pdf_path:
            logger.info(f"[SUCCESS] Cover Letter PDF: {cover_letter_pdf_path}")
        return metrics
        
    except Exception as ex:
        metrics["error"] = str(ex)
        logger.error(f"Packaging failed: {ex}")
        return metrics


async def master_pipeline(company_slug: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes the full end-to-end Phase 6 pipeline:
    Scrape -> Score -> Tailor -> Package for jobs scoring >= 3.5.
    """
    metrics = {
        "scraped": 0,
        "scored": 0,
        "tailored": 0,
        "packaged": 0
    }
    
    logger.info("Starting Master Pipeline End-to-End Run...")
    
    # 1. Scrape
    scrape_metrics = await scrape_pipeline(company_slug=company_slug)
    metrics["scraped"] = scrape_metrics.get("jobs_saved", 0)
    
    # 2. Score unscored jobs (Only for the requested company to save API quota!)
    score_metrics = await score_pipeline(company_slug=company_slug, dry_run=False)
    metrics["scored"] = score_metrics.get("jobs_evaluated", 0)
    
    # Identify which jobs advanced (score >= 3.5 and no existing package)
    from python.db.client import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    # Find jobs that have a score >= 3.5 but don't have a 'ready' application yet
    cursor.execute("""
    SELECT j.id 
    FROM jobs j
    JOIN scores s ON j.id = s.job_id
    LEFT JOIN applications a ON j.id = a.job_id
    WHERE s.overall_score >= 3.5 
      AND (a.id IS NULL OR a.status != 'ready')
    """)
    jobs_to_tailor = [row['id'] for row in cursor.fetchall()]
    conn.close()
    
    # 3 & 4. Tailor and Package
    for job_id in jobs_to_tailor:
        try:
            tailor_res = await tailor_pipeline(job_id=str(job_id))
            if tailor_res.get("success"):
                metrics["tailored"] += 1
                
                # Package PDF
                package_res = await package_pipeline(job_id=str(job_id))
                if package_res.get("success"):
                    metrics["packaged"] += 1
        except Exception as ex:
            logger.error(f"Failed to process job {job_id} in master pipeline: {ex}")
            
        # Rate limit mitigation for NIM (40 req/min)
        await asyncio.sleep(2.0)
            
    logger.info(f"Master Pipeline Complete. Scraped: {metrics['scraped']}, Scored: {metrics['scored']}, Packaged: {metrics['packaged']}.")
    return metrics

async def process_single_job(job_id: str) -> Dict[str, Any]:
    """
    Scores a single job. If the score is >= 3.5, it tailors and packages it.
    """
    metrics = {
        "success": False,
        "job_id": job_id,
        "scored": False,
        "advanced": False,
        "tailored": False,
        "packaged": False,
        "error": None
    }
    logger.info(f"Starting single-job pipeline for '{job_id}'...")
    
    # 1. Score
    score_res = await score_pipeline(job_id=job_id, dry_run=False)
    metrics["scored"] = True
    
    # Check score
    from python.db.client import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT overall_score FROM scores WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        metrics["error"] = "Failed to retrieve score for job."
        return metrics
        
    score = row['overall_score']
    if score >= 3.5:
        metrics["advanced"] = True
        logger.info(f"Job {job_id} scored {score}. Proceeding to tailor and package.")
        
        # 2. Tailor
        tailor_res = await tailor_pipeline(job_id=job_id)
        if tailor_res.get("success"):
            metrics["tailored"] = True
            
            # 3. Package
            pkg_res = await package_pipeline(job_id=job_id)
            if pkg_res.get("success"):
                metrics["packaged"] = True
                metrics["success"] = True
            else:
                metrics["error"] = pkg_res.get("error")
        else:
            metrics["error"] = tailor_res.get("error")
    else:
        logger.info(f"Job {job_id} scored {score} (< 3.5). Stopping pipeline.")
        metrics["success"] = True # It succeeded in processing, just didn't advance
        
    return metrics

async def validate_pipeline(job_id: str) -> Dict[str, Any]:
    """
    Validates a tailored resume PDF's page fill consistency.
    Re-renders the PDF using the TS generator and reports page fill percentage.
    """
    from python.utils.pdf_bridge import generate_pdf
    from PyPDF2 import PdfReader
    
    metrics = {
        "success": False,
        "job_id": job_id,
        "pdf_path": None,
        "page_fill": 0,
        "initial_fill": 0,
        "page_count": None,
        "error": None
    }
    
    try:
        app = get_application_by_job(job_id)
        if not app or not app.resume_version_id:
            raise ValueError(f"No tailored application/resume version found for job ID {job_id}. Please run the tailor command first.")
            
        # Fetch the resume version directly
        from python.db.client import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT resume_md, cover_letter, pdf_path FROM resume_versions WHERE id = ?", (str(app.resume_version_id),))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise ValueError(f"ResumeVersion ID {app.resume_version_id} not found in database.")
            
        resume_md = row['resume_md']
        logger.info(f"Re-rendering and validating PDF for job '{job_id}'...")
        
        # Re-render PDF and capture fill ratio
        pdf_path, page_fill, initial_fill = await generate_pdf(resume_md, job_id)
        
        # Determine page count using PyPDF2
        try:
            pdf_reader = PdfReader(pdf_path)
            page_count = len(pdf_reader.pages)
        except Exception as e:
            logger.error(f"Failed to read PDF page count: {e}")
            page_count = None
            
        metrics["success"] = True
        metrics["pdf_path"] = pdf_path
        metrics["page_fill"] = page_fill
        metrics["initial_fill"] = initial_fill
        metrics["page_count"] = page_count
        return metrics
        
    except Exception as ex:
        metrics["error"] = str(ex)
        logger.error(f"Validation failed: {ex}")
        return metrics
