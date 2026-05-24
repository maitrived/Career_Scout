import os
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Optional
from playwright.async_api import async_playwright, Page

from python.db.client import (
    get_job,
    get_application_by_job,
    get_connection,
    mark_applied,
)
from python.db.models import Job, Application

logger = logging.getLogger(__name__)


# Core resume schema for autofilling static credentials
def load_resume_json() -> dict:
    try:
        resume_path = Path("data/resume.json")
        if not resume_path.exists():
            resume_path = (
                Path(__file__).resolve().parent.parent.parent / "data" / "resume.json"
            )
        with open(resume_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        logger.error(f"Error loading resume.json for autofill: {ex}")
        return {}


async def fill_by_selector_or_label(
    page: Page, selectors: List[str], label_texts: List[str], value: str
) -> bool:
    """
    Attempts to fill an input field using selectors, falling back to label text matching.
    """
    # 1. Try selectors first
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if (
                await loc.count() > 0
                and await loc.first.is_visible()
                and await loc.first.is_editable()
            ):
                await loc.first.fill(value)
                return True
        except Exception:
            pass

    # 2. Try label text matching
    for label in label_texts:
        try:
            # Match exact or near text labels
            label_loc = page.locator(f'label:has-text("{label}")')
            count = await label_loc.count()
            for i in range(count):
                loc = label_loc.nth(i)
                for_id = await loc.get_attribute("for")
                if for_id:
                    input_loc = page.locator(f"#{for_id}")
                    if await input_loc.is_visible() and await input_loc.is_editable():
                        await input_loc.fill(value)
                        return True
        except Exception:
            pass

    # 3. Last resort: Match by name/id/placeholder matching keywords
    try:
        inputs = page.locator("input, textarea")
        count = await inputs.count()
        for i in range(count):
            inp = inputs.nth(i)
            name = (await inp.get_attribute("name") or "").lower()
            placeholder = (await inp.get_attribute("placeholder") or "").lower()
            id_val = (await inp.get_attribute("id") or "").lower()

            for keyword in label_texts:
                kw = keyword.lower()
                if kw in name or kw in placeholder or kw in id_val:
                    if await inp.is_visible() and await inp.is_editable():
                        await inp.fill(value)
                        return True
    except Exception:
        pass

    return False


async def upload_file_by_selector_or_label(
    page: Page, selectors: List[str], label_texts: List[str], file_path: str
) -> bool:
    """
    Attempts to upload a file using selectors, falling back to label text matching.
    """
    abs_path = str(Path(file_path).resolve())
    if not os.path.exists(abs_path):
        logger.error(f"File path does not exist for upload: {abs_path}")
        return False

    # 1. Try selectors
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.set_input_files(abs_path)
                return True
        except Exception:
            pass

    # 2. Try file inputs directly
    try:
        inputs = page.locator('input[type="file"]')
        count = await inputs.count()
        for i in range(count):
            inp = inputs.nth(i)
            id_val = (await inp.get_attribute("id") or "").lower()
            name = (await inp.get_attribute("name") or "").lower()
            for label in label_texts:
                lbl = label.lower()
                if lbl in id_val or lbl in name:
                    await inp.set_input_files(abs_path)
                    return True
    except Exception:
        pass

    # 3. Try label text matching
    for label in label_texts:
        try:
            label_loc = page.locator(f'label:has-text("{label}")')
            count = await label_loc.count()
            for i in range(count):
                loc = label_loc.nth(i)
                for_id = await loc.get_attribute("for")
                if for_id:
                    file_input = page.locator(f"#{for_id}")
                    await file_input.set_input_files(abs_path)
                    return True
        except Exception:
            pass

    return False


async def autofill_greenhouse(
    page: Page,
    resume: dict,
    pdf_path: str,
    cover_letter: str,
    cover_letter_pdf_path: str | None = None,
):
    """Fills out standard Greenhouse board elements."""
    contact = resume.get("contact", {})
    name_parts = resume.get("name", "").split(" ")
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    # Basic Info
    await fill_by_selector_or_label(
        page, ["input#first_name"], ["First Name"], first_name
    )
    await fill_by_selector_or_label(page, ["input#last_name"], ["Last Name"], last_name)
    await fill_by_selector_or_label(
        page, ["input#email"], ["Email"], contact.get("email", "")
    )
    await fill_by_selector_or_label(
        page, ["input#phone"], ["Phone"], contact.get("phone", "")
    )

    # Resume Upload
    # Greenhouse standard file input is input#resume or a file input with id contains resume
    uploaded = await upload_file_by_selector_or_label(
        page,
        [
            "input#resume",
            "input[type='file'][id*='resume']",
            "input[type='file'][accept*='pdf']",
        ],
        ["Resume", "CV"],
        pdf_path,
    )
    if uploaded:
        logger.info("Successfully uploaded resume PDF to Greenhouse form.")
    else:
        logger.warning("Could not upload resume PDF. Manual action required.")

    # Cover Letter pasting
    # Greenhouse has an optional "Paste Cover Letter" button that reveals a text area.
    # Selector: button[data-source="paste"] under #cover_letter_action_buttons
    try:
        paste_btn = page.locator('button[data-source="paste"]').first
        if await paste_btn.count() > 0 and await paste_btn.is_visible():
            await paste_btn.click()
            await asyncio.sleep(0.5)
    except Exception:
        pass

    cl_filled = await fill_by_selector_or_label(
        page,
        [
            "textarea#cover_letter_text",
            "textarea#cover_letter",
            "textarea[name*='cover_letter']",
        ],
        ["Cover Letter"],
        cover_letter,
    )
    if cl_filled:
        logger.info("Successfully pasted Cover Letter into Greenhouse form.")
    else:
        # Try to upload cover letter file instead if available
        if cover_letter_pdf_path:
            uploaded_cl = await upload_file_by_selector_or_label(
                page,
                [
                    "input[type='file'][id*='cover']",
                    "input[type='file'][name*='cover']",
                ],
                ["Cover Letter", "cover_letter", "coverletter"],
                cover_letter_pdf_path,
            )
            if uploaded_cl:
                logger.info(
                    "Successfully uploaded cover letter PDF to Greenhouse form."
                )
            else:
                logger.debug(
                    "Cover letter upload not found for Greenhouse; left as pasted text or manual upload required."
                )

    # Links
    await fill_by_selector_or_label(
        page,
        ["input[autocomplete*='linkedin']", "input[name*='linkedin']"],
        ["LinkedIn"],
        contact.get("linkedin", ""),
    )
    await fill_by_selector_or_label(
        page,
        ["input[autocomplete*='github']", "input[name*='github']"],
        ["GitHub"],
        contact.get("github", ""),
    )
    await fill_by_selector_or_label(
        page,
        ["input[name*='website']", "input[name*='portfolio']"],
        ["Portfolio", "Website"],
        contact.get("portfolio", ""),
    )


async def autofill_lever(
    page: Page,
    resume: dict,
    pdf_path: str,
    cover_letter: str,
    cover_letter_pdf_path: str | None = None,
):
    """Fills out standard Lever board elements."""
    contact = resume.get("contact", {})

    # Lever uses 'name' full instead of first/last
    await fill_by_selector_or_label(
        page, ["input[name='name']"], ["Full Name", "Name"], resume.get("name", "")
    )
    await fill_by_selector_or_label(
        page, ["input[name='email']"], ["Email"], contact.get("email", "")
    )
    await fill_by_selector_or_label(
        page, ["input[name='phone']"], ["Phone"], contact.get("phone", "")
    )
    await fill_by_selector_or_label(
        page,
        ["input[name='org']"],
        ["Current company", "Organization"],
        "Vybd (formerly BulkMagic)",
    )

    # Resume Upload (input#resume-upload-input)
    uploaded = await upload_file_by_selector_or_label(
        page,
        ["input#resume-upload-input", "input[type='file']"],
        ["Resume", "CV"],
        pdf_path,
    )
    if uploaded:
        logger.info("Successfully uploaded resume PDF to Lever form.")

    # Links
    await fill_by_selector_or_label(
        page,
        ["input[name='urls[LinkedIn]']"],
        ["LinkedIn"],
        contact.get("linkedin", ""),
    )
    await fill_by_selector_or_label(
        page, ["input[name='urls[GitHub]']"], ["GitHub"], contact.get("github", "")
    )
    await fill_by_selector_or_label(
        page,
        ["input[name='urls[Portfolio]']", "input[name='urls[Twitter]']"],
        ["Portfolio", "Website"],
        contact.get("portfolio", ""),
    )

    # Cover Letter / Additional Info
    cl_filled = await fill_by_selector_or_label(
        page,
        ["textarea[name='comments']", "textarea#additional-information"],
        ["Cover Letter", "Additional Information"],
        cover_letter,
    )
    if not cl_filled and cover_letter_pdf_path:
        uploaded_cl = await upload_file_by_selector_or_label(
            page,
            [
                "input[type='file'][id*='cover']",
                "input[type='file'][name*='cover']",
                "input[type='file'][id*='cover_letter']",
            ],
            ["Cover Letter", "cover_letter", "coverletter"],
            cover_letter_pdf_path,
        )
        if uploaded_cl:
            logger.info("Successfully uploaded cover letter PDF to Lever form.")


async def autofill_ashby(
    page: Page,
    resume: dict,
    pdf_path: str,
    cover_letter: str,
    cover_letter_pdf_path: str | None = None,
):
    """Fills out standard Ashby board elements."""
    contact = resume.get("contact", {})
    name_parts = resume.get("name", "").split(" ")
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    # Ashby forms are highly custom, so we rely strongly on labels and placeholders
    await fill_by_selector_or_label(
        page,
        ["input[name*='firstName']", "input#firstName"],
        ["First Name"],
        first_name,
    )
    await fill_by_selector_or_label(
        page, ["input[name*='lastName']", "input#lastName"], ["Last Name"], last_name
    )
    await fill_by_selector_or_label(
        page,
        ["input[name*='email']", "input#email", "input[type='email']"],
        ["Email"],
        contact.get("email", ""),
    )
    await fill_by_selector_or_label(
        page,
        ["input[name*='phone']", "input#phone", "input[type='tel']"],
        ["Phone"],
        contact.get("phone", ""),
    )

    # Resume Upload
    uploaded = await upload_file_by_selector_or_label(
        page, ["input[type='file']"], ["Resume", "CV"], pdf_path
    )
    if uploaded:
        logger.info("Successfully uploaded resume PDF to Ashby form.")

    # Links
    await fill_by_selector_or_label(
        page, ["input[name*='linkedin']"], ["LinkedIn"], contact.get("linkedin", "")
    )
    await fill_by_selector_or_label(
        page, ["input[name*='github']"], ["GitHub"], contact.get("github", "")
    )
    await fill_by_selector_or_label(
        page,
        ["input[name*='portfolio']", "input[name*='website']"],
        ["Portfolio", "Website"],
        contact.get("portfolio", ""),
    )

    # Cover letter
    cl_filled = await fill_by_selector_or_label(
        page,
        ["textarea[name*='coverLetter']", "textarea[placeholder*='cover letter']"],
        ["Cover Letter"],
        cover_letter,
    )
    if not cl_filled and cover_letter_pdf_path:
        uploaded_cl = await upload_file_by_selector_or_label(
            page,
            ["input[type='file']"],
            ["Cover Letter", "cover_letter", "coverletter"],
            cover_letter_pdf_path,
        )
        if uploaded_cl:
            logger.info("Successfully uploaded cover letter PDF to Ashby form.")


async def autofill_job_by_url(
    page: Page,
    job: Job,
    resume_json: dict,
    pdf_path: str,
    cover_letter: str,
    cover_letter_pdf_path: str | None = None,
):
    """
    Directs filling depending on which portal domain we detect in the URL.
    """
    url = job.url.lower()

    logger.info(f"Navigating to {job.company} application: {job.url}")
    await page.goto(job.url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)  # Give 2s for DOM rendering

    if "greenhouse.io" in url or "boards.greenhouse.io" in url:
        await autofill_greenhouse(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
        )
    elif "lever.co" in url or "jobs.lever.co" in url:
        await autofill_lever(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
        )
    elif "ashbyhq.com" in url or "jobs.ashbyhq.com" in url:
        await autofill_ashby(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
        )
    else:
        # Generic fallback
        logger.warning("Unrecognized domain. Applying fallback form filling...")
        contact = resume_json.get("contact", {})
        await fill_by_selector_or_label(
            page, [], ["First Name", "Name"], resume_json.get("name", "")
        )
        await fill_by_selector_or_label(
            page, [], ["Last Name"], resume_json.get("name", "").split(" ")[-1]
        )
        await fill_by_selector_or_label(page, [], ["Email"], contact.get("email", ""))
        await fill_by_selector_or_label(page, [], ["Phone"], contact.get("phone", ""))
        await fill_by_selector_or_label(
            page, [], ["LinkedIn"], contact.get("linkedin", "")
        )
        await fill_by_selector_or_label(page, [], ["GitHub"], contact.get("github", ""))
        await upload_file_by_selector_or_label(page, [], ["Resume", "CV"], pdf_path)
        # Try paste first, then attempt file upload for cover letter if available
        pasted = await fill_by_selector_or_label(
            page, [], ["Cover Letter"], cover_letter
        )
        if not pasted and cover_letter_pdf_path:
            await upload_file_by_selector_or_label(
                page, [], ["Cover Letter", "cover_letter"], cover_letter_pdf_path
            )

    # Question Handler for extra/custom questions
    try:
        from python.utils.question_handler import QuestionHandler

        qh = QuestionHandler()
        await qh.handle_extra_questions(page, job)
    except Exception as ex:
        logger.error(f"Error executing QuestionHandler: {ex}")


async def run_multi_tab_autofill(job_ids: List[str]):
    """
    Launches headful browser and opens each job ID in a separate tab, fills standard fields,
    and pauses for the user to manually review, submit, and confirm in console.
    """
    if not job_ids:
        logger.warning("No job IDs provided to autofill.")
        return

    resume_json = load_resume_json()
    if not resume_json:
        logger.error("Failed to load resume.json. Aborting autofill.")
        return

    # Fetch data details for all job_ids first
    jobs_data = []
    for job_id in job_ids:
        job = get_job(job_id)
        if not job:
            logger.error(f"Job ID {job_id} not found.")
            continue

        app = get_application_by_job(job_id)
        if not app or not app.resume_version_id:
            logger.error(
                f"No tailored application version found for job '{job.title}' ({job_id}). Please tailor first."
            )
            continue

        # Fetch PDF path and cover letter from DB
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT resume_md, cover_letter, pdf_path, cover_letter_pdf_path FROM resume_versions WHERE id = ?",
            (str(app.resume_version_id),),
        )
        row = cursor.fetchone()
        conn.close()

        if not row or not row["pdf_path"]:
            logger.error(
                f"Tailored PDF path not found for application version {app.resume_version_id}."
            )
            continue

        cover_letter_pdf = (
            row["cover_letter_pdf_path"]
            if "cover_letter_pdf_path" in row.keys()
            else None
        )
        jobs_data.append(
            {
                "job": job,
                "pdf_path": row["pdf_path"],
                "cover_letter": row["cover_letter"],
                "cover_letter_pdf_path": cover_letter_pdf,
            }
        )

    if not jobs_data:
        logger.error("No valid applications resolved for auto-filling. Aborting.")
        return

    logger.info(
        f"Starting Playwright headful session to fill {len(jobs_data)} applications..."
    )

    async with async_playwright() as p:
        # Launch Chromium headfully so user can inspect and submit
        browser = await p.chromium.launch(headless=False)
        # Use a maximized window size or default desktop size
        context = await browser.new_context(viewport={"width": 1280, "height": 800})

        pages = []
        for index, item in enumerate(jobs_data):
            job = item["job"]
            pdf_path = item["pdf_path"]
            cover_letter = item["cover_letter"]

            logger.info(
                f"[{index + 1}/{len(jobs_data)}] Opening tab for: {job.title} at {job.company}"
            )

            # Create a tab
            page = await context.new_page()
            pages.append(page)

            try:
                await autofill_job_by_url(
                    page,
                    job,
                    resume_json,
                    pdf_path,
                    cover_letter,
                    item.get("cover_letter_pdf_path"),
                )
            except Exception as ex:
                logger.error(f"Failed to fill form for {job.title}: {ex}")

        # Keep browser open and wait for human input in the console
        print("\n" + "=" * 80)
        print("PLAYWRIGHT AUTO-FILLER HAS COMPLETED.")
        print(
            "Please click through each tab in the opened Chrome browser window, answer custom questions, and click submit."
        )
        print("=" * 80 + "\n")

        # Block until user hits Enter in the console
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            input,
            "Press [Enter] in this terminal when you have finished submitting ALL applications to close the browser...",
        )

        # Confirm applications that were submitted
        print("\nUpdating database statuses...")
        for item in jobs_data:
            job = item["job"]
            # Prompt user for each job to make sure they actually submitted it
            user_confirm = ""
            while user_confirm.lower() not in ["y", "n"]:
                user_confirm = input(
                    f"Did you successfully submit application for '{job.title}' at '{job.company}'? (y/n): "
                )

            if user_confirm.lower() == "y":
                mark_applied(job.id, "applied")
                print(f"✓ Marked {job.company} - {job.title} as 'applied' in DB.")
            else:
                print(f"✗ Left {job.company} - {job.title} as 'ready'.")

        await browser.close()
        logger.info("Playwright session terminated.")
