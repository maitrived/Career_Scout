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


async def _smart_fill_element(page: Page, element, value: str) -> bool:
    """
    Fills a single element smartly:
    - Native <select>: uses select_option() with fuzzy matching
    - React Select / custom autocomplete: opens menu then clicks matching option
    - Text/textarea: uses fill()
    """
    try:
        tag = await element.evaluate("el => el.tagName.toLowerCase()")
        el_type = (await element.get_attribute("type") or "").lower()

        # --- React Select detection: check if input lives inside a [class*="select__control"] ---
        is_react_select = await element.evaluate("""el => {
            let curr = el.parentElement;
            for (let i = 0; i < 5; i++) {
                if (!curr) break;
                if (curr.className && curr.className.includes('select__control')) return true;
                if (curr.className && curr.className.includes('Select__control')) return true;
                curr = curr.parentElement;
            }
            return false;
        }""")
        if is_react_select:
            # Click to open menu, type to filter, then click the right option
            try:
                await element.click()
                await asyncio.sleep(0.3)
                await element.fill(value)
                await asyncio.sleep(1.0)
                # Find the option in the React Select menu
                for sel in [
                    f'[class*="select__option"]:has-text("{value}")',
                    '[class*="select__option"]',
                    f'[class*="Select__option"]:has-text("{value}")',
                    '[class*="Select__option"]',
                ]:
                    try:
                        opts = page.locator(sel)
                        count = await opts.count()
                        val_lower = value.lower()
                        for i in range(min(count, 20)):
                            opt = opts.nth(i)
                            if not await opt.is_visible():
                                continue
                            text = (await opt.inner_text()).strip().lower()
                            if val_lower in text or text in val_lower:
                                await opt.click()
                                return True
                        if count == 1 and await opts.first.is_visible():
                            await opts.first.click()
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

        # --- Native <select> dropdown ---
        if tag == "select":
            # 1. Try exact label match
            try:
                await element.select_option(label=value)
                return True
            except Exception:
                pass
            # 2. Try exact value match
            try:
                await element.select_option(value=value)
                return True
            except Exception:
                pass
            # 3. Fuzzy match against all options
            try:
                options = await element.evaluate(
                    "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                )
                val_lower = value.lower()
                for opt in options:
                    if val_lower in opt["text"].lower() or val_lower in opt["value"].lower():
                        await element.select_option(value=opt["value"])
                        return True
            except Exception:
                pass
            return False

        # --- Skip non-fillable types ---
        if el_type in ["file", "submit", "button", "hidden", "image", "checkbox"]:
            return False

        # --- Radio inputs: select matching radio in the group by name/value/label ---
        if el_type == "radio":
            try:
                name = await element.get_attribute("name") or ""
                val_lower = value.lower()
                if name:
                    radios = page.locator(f'input[type="radio"][name="{name}"]')
                    count = await radios.count()
                    for i in range(count):
                        r = radios.nth(i)
                        if not await r.is_visible():
                            continue
                        rv = (await r.get_attribute("value") or "").strip().lower()
                        if rv and (val_lower in rv or rv in val_lower):
                            await r.click()
                            return True
                        al = (await r.get_attribute("aria-label") or "").strip().lower()
                        if al and (val_lower in al or al in val_lower):
                            await r.click()
                            return True
                        rid = await r.get_attribute("id")
                        if rid:
                            lbl = page.locator(f'label:has([for="{rid}"])')
                            if await lbl.count() > 0 and await lbl.first.is_visible():
                                text = (await lbl.first.inner_text()).strip().lower()
                                if val_lower in text or text in val_lower:
                                    await r.click()
                                    return True
                    # If only one visible radio, click it
                    if count == 1 and await radios.first.is_visible():
                        await radios.first.click()
                        return True
            except Exception:
                pass
            return False

        # --- Standard text / textarea: fill then check for autocomplete suggestions ---
        await element.fill(value)
        await asyncio.sleep(1.0)  # Give JS time to render the dropdown

        # Check if a suggestion dropdown appeared (covers React Select, Selectize, Chosen, custom)
        suggestion_selectors = [
            # Exact text match first (fastest)
            f'[role="option"]:has-text("{value}")',
            # React Select v5/v6
            '[class*="select__option"]',
            '[class*="Select__option"]',
            '[class*="select__menu"] [class*="option"]',
            # Headless UI / Radix
            '[role="listbox"] [role="option"]',
            '[role="listbox"] li',
            # Generic
            'li[role="option"]',
            '.dropdown-item',
            'ul.suggestions li',
            '[data-testid*="option"]',
            '[class*="suggestion"]',
            '[class*="autocomplete"] li',
            '[class*="dropdown"] li',
            '[class*="menu-item"]',
            # Greenhouse/Lever specific
            '.select-dropdown li',
            '.option-list li',
        ]
        val_lower = value.lower()
        for sel in suggestion_selectors:
            try:
                opts = page.locator(sel)
                count = await opts.count()
                if count == 0:
                    continue
                for i in range(min(count, 20)):
                    opt = opts.nth(i)
                    if not await opt.is_visible():
                        continue
                    text = (await opt.inner_text()).strip().lower()
                    if val_lower in text or text in val_lower:
                        await opt.click()
                        return True
                # If only one option visible, click it
                if count == 1 and await opts.first.is_visible():
                    await opts.first.click()
                    return True
            except Exception:
                continue

        return True  # fill() was called even if no autocomplete matched

    except Exception:
        pass
    return False


async def fill_by_selector_or_label(
    page: Page, selectors: List[str], label_texts: List[str], value: str
) -> bool:
    """
    Attempts to fill an input field, select option, or custom dropdown using selectors,
    falling back to label text matching. Handles native <select>, autocomplete, and text inputs.
    """
    # ── Step 1: Try explicit selectors ────────────────────────────────────────
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                if await _smart_fill_element(page, loc.first, value):
                    return True
        except Exception:
            pass

    # ── Step 2: Try label text matching ───────────────────────────────────────
    for label in label_texts:
        try:
            label_loc = page.locator(f'label:has-text("{label}")')
            count = await label_loc.count()
            for i in range(count):
                lbl = label_loc.nth(i)
                for_id = await lbl.get_attribute("for")
                if for_id:
                    target = page.locator(f"#{for_id}")
                    if await target.count() > 0 and await target.is_visible():
                        if await _smart_fill_element(page, target, value):
                            return True
        except Exception:
            pass

    # ── Step 3: Scan by name/id/placeholder attribute keywords ────────────────
    try:
        inputs = page.locator("input, textarea, select")
        count = await inputs.count()
        for i in range(count):
            inp = inputs.nth(i)
            name = (await inp.get_attribute("name") or "").lower()
            placeholder = (await inp.get_attribute("placeholder") or "").lower()
            id_val = (await inp.get_attribute("id") or "").lower()
            for keyword in label_texts:
                kw = keyword.lower()
                if kw in name or kw in placeholder or kw in id_val:
                    if await inp.is_visible():
                        if await _smart_fill_element(page, inp, value):
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

    # 1. Try selectors (iterate matches so we can prefer labeled elements and avoid reusing inputs)
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            if count == 0:
                continue
            # Prefer elements whose attributes/labels match label_texts
            for i in range(count):
                candidate = loc.nth(i)
                if not await candidate.is_visible():
                    continue
                # Skip if already used by previous upload
                used = (await candidate.get_attribute("data-scout-uploaded"))
                if used:
                    continue
                # If selector is generic (like input[type='file']) and label_texts provided,
                # check associated label/attributes for hints
                if sel.strip() in ("input[type='file']", "input[type=\"file\"]") and label_texts:
                    combined = ""
                    try:
                        outer = await candidate.evaluate("el => el.closest('div') ? el.closest('div').innerText.toLowerCase() : ''")
                        combined = outer
                    except Exception:
                        combined = ""
                    attrs = " ".join(filter(None, [await candidate.get_attribute('id') or '', await candidate.get_attribute('name') or '', await candidate.get_attribute('aria-label') or ''])).lower()
                    # try associated label
                    lbl_text = ""
                    try:
                        id_val = await candidate.get_attribute('id')
                        if id_val:
                            lbl = page.locator(f"label[for='{id_val}']")
                            if await lbl.count() > 0:
                                lbl_text = (await lbl.first.inner_text()).lower()
                    except Exception:
                        lbl_text = ""
                    combined = f"{combined} {attrs} {lbl_text}"
                    matched = False
                    for kw in label_texts:
                        if kw.lower() in combined:
                            matched = True
                            break
                    if not matched:
                        # skip this candidate since it doesn't match any label hints
                        continue

                # Set files and mark as used
                try:
                    await candidate.set_input_files(abs_path)
                    # mark as used with filename to avoid reusing same element for cover letter
                    fname = Path(abs_path).name
                    await candidate.evaluate(f"el => el.setAttribute('data-scout-uploaded', '{fname}')")
                    logger.info(f"Uploaded file '{fname}' using selector '{sel}'")
                    return True
                except Exception:
                    continue
        except Exception:
            pass

    # 2. Try file inputs directly (inspect each and prefer ones matching label_texts; skip already-used inputs)
    try:
        inputs = page.locator('input[type="file"]')
        count = await inputs.count()
        for i in range(count):
            inp = inputs.nth(i)
            if not await inp.is_visible():
                continue
            used = (await inp.get_attribute("data-scout-uploaded"))
            if used:
                continue
            id_val = (await inp.get_attribute("id") or "").lower()
            name = (await inp.get_attribute("name") or "").lower()
            aria = (await inp.get_attribute("aria-label") or "").lower()
            # check associated label text
            label_text = ""
            try:
                idv = await inp.get_attribute('id')
                if idv:
                    lbl = page.locator(f"label[for='{idv}']")
                    if await lbl.count() > 0:
                        label_text = (await lbl.first.inner_text()).lower()
            except Exception:
                label_text = ""

            combined = f"{id_val} {name} {aria} {label_text}"
            matched = False
            for label in label_texts:
                if label.lower() in combined:
                    matched = True
                    break
            if matched or not label_texts:
                try:
                    await inp.set_input_files(abs_path)
                    fname = Path(abs_path).name
                    await inp.evaluate(f"el => el.setAttribute('data-scout-uploaded', '{fname}')")
                    logger.info(f"Uploaded file '{fname}' via file input selection (matched labels={label_texts})")
                    return True
                except Exception:
                    continue
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
                    if await file_input.count() > 0:
                        try:
                            await file_input.first.set_input_files(abs_path)
                            fname = Path(abs_path).name
                            await file_input.first.evaluate(f"el => el.setAttribute('data-scout-uploaded', '{fname}')")
                            logger.info(f"Uploaded file '{fname}' via label match for '{label}'")
                            return True
                        except Exception:
                            continue
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
    # Some Ashby/UIs present an early "Autofill from resume" prompt. To avoid
    # uploading into that prompt, manually scan visible file inputs and pick the
    # one whose nearest label/id/name suggests it's the actual Resume upload.
    try:
        file_inputs = page.locator("input[type='file']")
        candidate = None
        count = await file_inputs.count()
        prefer_keywords = ["resume", "cv", "curriculum", "upload resume"]
        avoid_keywords = ["autofill", "autofill from resume", "paste resume"]
        for i in range(count):
            inp = file_inputs.nth(i)
            if not await inp.is_visible():
                continue
            # Skip inputs inside autofill prompt containers
            try:
                outer_text = await inp.evaluate("el => el.closest('div') ? el.closest('div').innerText.toLowerCase() : ''")
            except Exception:
                outer_text = ""
            if any(a in outer_text for a in avoid_keywords):
                continue

            # Check attributes and associated label
            attrs = " ".join(filter(None, [await inp.get_attribute('id') or '', await inp.get_attribute('name') or '', await inp.get_attribute('aria-label') or ''])).lower()
            label_text = ""
            try:
                id_val = await inp.get_attribute('id')
                if id_val:
                    lbl = page.locator(f"label[for='{id_val}']")
                    if await lbl.count() > 0:
                        label_text = (await lbl.first.inner_text()).lower()
            except Exception:
                label_text = ""

            combined = f"{outer_text} {attrs} {label_text}"
            logger.debug(f"File input candidate combined context: {combined}")
            if any(k in combined for k in prefer_keywords):
                candidate = inp
                break

        if candidate:
            # Use the chosen input
            await candidate.set_input_files(str(Path(pdf_path).resolve()))
            try:
                fname = Path(pdf_path).name
                await candidate.evaluate(f"el => el.setAttribute('data-scout-uploaded', '{fname}')")
            except Exception:
                pass
            uploaded = True
        else:
            # Fallback to helper
            uploaded = await upload_file_by_selector_or_label(
                page,
                [
                    "input[id*='resume']",
                    "input[name*='resume']",
                    "input[aria-label*='resume']",
                    "input[type='file'][accept*='pdf']",
                ],
                ["Resume", "CV"],
                pdf_path,
            )
    except Exception:
        uploaded = False
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


async def autofill_generic(
    page: Page,
    resume_json: dict,
    pdf_path: str,
    cover_letter: str,
    cover_letter_pdf_path: str | None = None,
):
    """Generic fallback form filler for unrecognized ATS domains."""
    logger.warning(f"Running generic fallback form filler on {page.url}...")
    contact = resume_json.get("contact", {})
    await fill_by_selector_or_label(
        page, [], ["First Name", "Name"], resume_json.get("name", "")
    )
    await fill_by_selector_or_label(
        page, [], ["Last Name"], resume_json.get("name", "").split(" ")[-1]
    )
    await fill_by_selector_or_label(page, [], ["Email"], contact.get("email", ""))
    await fill_by_selector_or_label(page, [], ["Phone"], contact.get("phone", ""))
    await fill_by_selector_or_label(page, [], ["LinkedIn"], contact.get("linkedin", ""))
    await fill_by_selector_or_label(page, [], ["GitHub"], contact.get("github", ""))
    await upload_file_by_selector_or_label(page, [], ["Resume", "CV"], pdf_path)
    # Try paste first, then attempt file upload for cover letter if available
    pasted = await fill_by_selector_or_label(page, [], ["Cover Letter"], cover_letter)
    if not pasted and cover_letter_pdf_path:
        await upload_file_by_selector_or_label(
            page, [], ["Cover Letter", "cover_letter"], cover_letter_pdf_path
        )


async def autofill_yc(
    page: Page,
    resume_json: dict,
    pdf_path: str,
    cover_letter: str,
    cover_letter_pdf_path: str | None = None,
):
    """Handles Y Combinator job postings which require clicking an 'Apply' button first."""
    logger.info("Attempting to click YC Apply button...")
    try:
        # Match 'Apply', 'Apply Now', 'Apply to role' (case insensitive using playwright's text matching)
        apply_btn = page.locator("button, a").filter(has_text="Apply to role ›")

        count = await apply_btn.count()
        clicked = False
        for i in range(count):
            btn = apply_btn.nth(i)
            if await btn.is_visible():
                # For YC links, it sometimes opens a new tab. In our setup, we can just click and wait.
                # If it opens a new tab, Playwright's `page` object won't switch automatically.
                # But typically 'Apply' either opens a modal or does same-tab navigation.
                await btn.click()
                clicked = True
                break

        if clicked:
            logger.info("Clicked YC Apply button. Waiting for form...")
            await page.wait_for_timeout(3000)
    except Exception as ex:
        logger.warning(f"Could not click YC Apply button: {ex}")

    # Now we check the URL, if it redirected to a known ATS, use that specific autofill.
    current_url = page.url.lower()
    if "greenhouse.io" in current_url:
        await autofill_greenhouse(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
        )
    elif "lever.co" in current_url:
        await autofill_lever(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
        )
    elif "ashbyhq.com" in current_url:
        await autofill_ashby(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
        )
    else:
        # Still on YC or unknown ATS. Run generic fallback.
        await autofill_generic(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
        )


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
    elif "ycombinator.com" in url:
        await autofill_yc(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
        )
    else:
        # Generic fallback
        await autofill_generic(
            page, resume_json, pdf_path, cover_letter, cover_letter_pdf_path
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
