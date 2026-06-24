import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from playwright.async_api import Page, Locator
from openai import OpenAI

from python.config import NIM_API_KEY, LLM_MODEL
from python.db.models import Job

logger = logging.getLogger(__name__)

class QuestionHandler:
    """
    Handles identifying, matching, and filling custom/complex questions on application forms.
    Uses a static qa_bank.json and dynamic star_bank.json with self-learning updates.
    """
    
    def __init__(self, qa_bank_path: str = "data/qa_bank.json", star_bank_path: str = "data/star_bank.json"):
        self.qa_bank_path = Path(qa_bank_path)
        self.star_bank_path = Path(star_bank_path)
        
        self.qa_bank = self._load_bank(self.qa_bank_path)
        self.star_bank = self._load_bank(self.star_bank_path)
        
        # Initialize OpenAI/NIM Client
        self.api_key = NIM_API_KEY
        if self.api_key:
            self.client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=self.api_key
            )
        else:
            self.client = None
            logger.warning("NIM_API_KEY not found. LLM generation of questions will be skipped.")
            
        self.model_name = LLM_MODEL
        self.resume_summary = self._load_resume_summary()

    def _load_bank(self, path: Path) -> Dict[str, Any]:
        """Loads a JSON question bank."""
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading question bank {path}: {e}")
            return {}

    def _save_bank(self, bank: Dict[str, Any], path: Path):
        """Saves a JSON question bank."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(bank, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving question bank {path}: {e}")

    def _load_resume_summary(self) -> str:
        """Loads a summary of the candidate's resume for LLM generation context."""
        try:
            resume_path = Path("data/resume.json")
            if resume_path.exists():
                with open(resume_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("summary", "")
            return "Parva: Python Backend Software Engineer, 2 YOE, GCP, FastAPI, PostgreSQL."
        except Exception as e:
            logger.error(f"Error loading resume summary: {e}")
            return ""

    def fuzzy_match(self, label: str, bank: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Fuzzy matches a label text against keywords in a question bank."""
        label_lower = label.lower().strip()
        best_key = None
        best_entry = None
        best_score = 0

        # Score matches by number of keyword hits and keyword length (prefer longer keywords)
        for key, entry in bank.items():
            keywords = entry.get("keywords", [])
            score = 0
            for kw in keywords:
                kw_clean = kw.lower().strip()
                # prefer whole-word matches using word boundaries
                try:
                    import re
                    if re.search(r"\b" + re.escape(kw_clean) + r"\b", label_lower):
                        score += 10 + len(kw_clean)
                    elif kw_clean in label_lower:
                        score += 1 + len(kw_clean)
                except Exception:
                    if kw_clean in label_lower:
                        score += 1
            if score > best_score:
                best_score = score
                best_key = key
                best_entry = entry

        # require a minimal score to accept a match
        if best_score >= 5:
            return best_key, best_entry
        return None, None

    async def get_label_text(self, page: Page, element) -> str:
        """Retrieves cleaned label or descriptive text associated with an input element."""
        try:
            type_attr = (await element.get_attribute("type") or "").lower()
            if type_attr in ["radio", "checkbox"]:
                # Try to get the group label (fieldset legend or nearby question)
                group_text = await element.evaluate("""el => {
                    const fieldset = el.closest('fieldset');
                    if (fieldset) {
                        const legend = fieldset.querySelector('legend');
                        if (legend) return legend.innerText || '';
                    }
                    // Fallback to searching up the tree for a container with text ending in ? or :
                    let curr = el.parentElement;
                    for (let i=0; i<4; i++) { // search up to 4 levels up
                        if (!curr) break;
                        const prev = curr.previousElementSibling;
                        if (prev && prev.innerText) {
                            if (prev.innerText.includes('?') || prev.innerText.includes('*')) {
                                return prev.innerText;
                            }
                        }
                        // Also check for a parent div with a question-like label before the inputs
                        const firstChild = curr.firstElementChild;
                        if (firstChild && firstChild !== el && firstChild.tagName !== 'INPUT') {
                             if (firstChild.innerText && (firstChild.innerText.includes('?') || firstChild.innerText.includes('*'))) {
                                 return firstChild.innerText;
                             }
                        }
                        curr = curr.parentElement;
                    }
                    return '';
                }""")
                if group_text.strip():
                    return group_text.strip()
            
            # 1. Look for <label for="id"> matching element id
            id_val = await element.get_attribute("id")
            if id_val:
                label_loc = page.locator(f"label[for='{id_val}']")
                if await label_loc.count() > 0:
                    txt = await label_loc.first.inner_text()
                    if txt.strip():
                        return txt.strip()
            
            # 2. Check if element is nested within a label
            nested_text = await element.evaluate("el => { const lbl = el.closest('label'); return lbl ? lbl.innerText : ''; }")
            if nested_text.strip():
                return nested_text.strip()
                
            # 3. Check for aria-label or placeholder
            aria_label = await element.get_attribute("aria-label")
            if aria_label and aria_label.strip():
                return aria_label.strip()
                
            placeholder = await element.get_attribute("placeholder")
            if placeholder and placeholder.strip():
                return placeholder.strip()
                
            # 4. Check sibling/parent text (common in custom forms)
            sibling_text = await element.evaluate("""el => {
                const parent = el.parentElement;
                if (!parent) return '';
                // Look for text nodes or child elements that are not inputs/selects
                for (let child of Array.from(parent.childNodes)) {
                    if (child !== el && child.nodeType === Node.ELEMENT_NODE && !['INPUT', 'SELECT', 'TEXTAREA'].includes(child.tagName)) {
                        const txt = child.innerText || '';
                        if (txt.trim()) return txt.trim();
                    }
                    if (child !== el && child.nodeType === Node.TEXT_NODE) {
                        const txt = child.textContent || '';
                        if (txt.trim()) return txt.trim();
                    }
                }
                // Try parent's header elements
                const header = parent.querySelector('h1, h2, h3, h4, h5, h6, legend, span, label');
                if (header) return header.innerText || '';
                return parent.innerText || '';
            }""")
            if sibling_text.strip():
                return sibling_text.strip()
                
        except Exception as e:
            logger.debug(f"Error resolving label text for element: {e}")
            
        return ""

    def generate_answer_via_llm(self, template: str, question: str, company: str, title: str, jd: str) -> str:
        """Calls NIM API to generate a tailored response to an open-ended/STAR question."""
        if not self.client:
            logger.warning("NIM client not initialized. Cannot generate answer.")
            return ""
            
        prompt = template.format(company=company, role=title)
        
        full_prompt = f"""
You are generating a professional job application answer for Parva.

RESUME SUMMARY:
{self.resume_summary}

JOB DETAIL:
- Company: {company}
- Role: {title}
- Job Description: {jd}

QUESTION:
{question}

INSTRUCTION FOR ANSWER:
{prompt}

RULES:
1. Return ONLY the direct answer text. Do NOT include quotes, intros, conversational filler, notes, or explanations.
2. Keep it fully truthful to Parva's actual experience (Python, FastAPI, Supabase, GCP, Vybd.ai, ASU).
3. Do NOT fabricate any details or exaggerate.
4. Keep it extremely concise and professional (max 2-3 sentences, 250 characters).
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.3,
                max_tokens=256
            )
            answer = response.choices[0].message.content.strip()
            # Strip trailing/leading quotes if the model wrapped the text
            if answer.startswith('"') and answer.endswith('"'):
                answer = answer[1:-1].strip()
            return answer
        except Exception as e:
            logger.error(f"Error generating answer via NIM API: {e}")
            return ""

    async def fill_element(self, page: Page, element, answer: str, label_text: str) -> bool:
        """Selects, clicks, or fills the appropriate field based on tag type and options."""
        try:
            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            type_attr = (await element.get_attribute("type") or "").lower()

            # --- React Select detection ---
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
                try:
                    await element.click()
                    import asyncio
                    await asyncio.sleep(0.3)
                    await element.fill(answer)
                    await asyncio.sleep(1.0)
                    for sel in [
                        f'[class*="select__option"]:has-text("{answer}")',
                        '[class*="select__option"]',
                        f'[class*="Select__option"]:has-text("{answer}")',
                        '[class*="Select__option"]',
                    ]:
                        try:
                            opts = page.locator(sel)
                            count = await opts.count()
                            val_lower = answer.lower()
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

            if tag_name == "select":
                # 1. Exact label match
                try:
                    await element.select_option(label=answer)
                    return True
                except Exception:
                    pass
                # 2. Exact value match
                try:
                    await element.select_option(value=answer)
                    return True
                except Exception:
                    pass
                # 3. Fuzzy: iterate options and pick partial match
                try:
                    options = await element.evaluate(
                        "el => Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))"
                    )
                    ans_lower = answer.lower()
                    for opt in options:
                        if ans_lower in opt["text"].lower() or ans_lower in opt["value"].lower():
                            await element.select_option(value=opt["value"])
                            return True
                except Exception:
                    pass

            elif tag_name == "input" and type_attr == "radio":
                radio_text = await element.evaluate("""el => {
                    const parent = el.parentElement;
                    if (parent && parent.tagName.toLowerCase() === 'label') return parent.innerText || '';
                    const id = el.getAttribute('id');
                    if (id) {
                        const lbl = document.querySelector(`label[for="${id}"]`);
                        if (lbl) return lbl.innerText || '';
                    }
                    return el.value || '';
                }""")
                if answer.lower() == radio_text.strip().lower() or answer.lower() in radio_text.strip().lower():
                    await element.click()
                    return True

            elif tag_name == "input" and type_attr == "checkbox":
                    # Handle both single boolean checkboxes and checkbox groups (multi-select)
                    try:
                        name = await element.get_attribute("name") or ""
                        ans_list = [a.strip().lower() for a in ((answer or "") if isinstance(answer, list) else str(answer)).split(",")]
                        if name:
                            boxes = page.locator(f'input[type="checkbox"][name="{name}"]')
                            count = await boxes.count()
                            for i in range(count):
                                b = boxes.nth(i)
                                if not await b.is_visible():
                                    continue
                                bval = (await b.get_attribute("value") or "").strip().lower()
                                blabel = ""
                                bid = await b.get_attribute("id")
                                if bid:
                                    lbl = page.locator(f"label[for='{bid}']")
                                    if await lbl.count() > 0:
                                        blabel = (await lbl.first.inner_text()).strip().lower()
                                # If any answer token matches value or label, ensure it's checked
                                matched = any(tok in bval or tok in blabel for tok in ans_list if tok)
                                is_checked = await b.is_checked()
                                if matched and not is_checked:
                                    await b.click()
                                if not matched and is_checked and len(ans_list) == 1 and ans_list[0] in ["no", "false", "none"]:
                                    await b.click()
                            return True
                    except Exception:
                        # fallback to boolean logic
                        should_check = answer.lower() in ["yes", "true", "1", "checked", "agree", "y"]
                        is_checked = await element.is_checked()
                        if should_check != is_checked:
                            await element.click()
                        return True

            else:
                # Standard text/textarea — fill then check for autocomplete suggestions
                await element.fill(answer)
                await asyncio.sleep(1.0)  # Give JS time to render the dropdown
                # Try to click a matching autocomplete suggestion if one appeared
                suggestion_selectors = [
                    # Exact text match first (fastest)
                    f'[role="option"]:has-text("{answer}")',
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
                    '[class*="suggestion"]',
                    '[class*="autocomplete"] li',
                    '[class*="dropdown"] li',
                    '[class*="menu-item"]',
                    # Greenhouse/Lever specific
                    '.select-dropdown li',
                    '.option-list li',
                ]
                ans_lower = answer.lower()
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
                            if ans_lower in text or text in ans_lower:
                                await opt.click()
                                return True
                        if count == 1 and await opts.first.is_visible():
                            await opts.first.click()
                            return True
                    except Exception:
                        continue
                return True

        except Exception as e:
            logger.error(f"Error filling element: {e}")

        return False


    async def handle_extra_questions(self, page: Page, job: Job):
        """
        Scans all visible unfilled input, textarea, and select fields.
        Answers them using qa_bank/star_bank or highlights them if unknown.
        """
        logger.info("Scanning for extra, custom questions on the application form...")
        
        # 1. Gather all inputs, selects, and textareas
        fields = page.locator("input, select, textarea")
        count = await fields.count()
        
        unfilled_fields = []
        
        for i in range(count):
            field = fields.nth(i)
            
            # Skip hidden, disabled, file inputs, submit buttons, and already filled inputs
            is_visible = await field.is_visible()
            if not is_visible:
                continue
                
            is_disabled = await field.is_disabled()
            if is_disabled:
                continue
                
            type_attr = (await field.get_attribute("type") or "").lower()
            if type_attr in ["file", "submit", "button", "hidden", "image"]:
                continue
                
            tag_name = await field.evaluate("el => el.tagName.toLowerCase()")
            if type_attr not in ["radio", "checkbox"]:
                val = (await field.input_value() if tag_name != "select" else await field.evaluate("el => el.value")) or ""
                if val.strip():
                    # Already filled by core/standard fill
                    continue
                
            unfilled_fields.append(field)
            
        logger.info(f"Found {len(unfilled_fields)} visible unfilled fields to evaluate.")
        
        for index, field in enumerate(unfilled_fields):
            label_text = await self.get_label_text(page, field)
            if not label_text:
                continue
                
            logger.info(f"Evaluating field [{index+1}/{len(unfilled_fields)}]: '{label_text}'")
            
            # A. First try static QA bank
            qa_key, qa_entry = self.fuzzy_match(label_text, self.qa_bank)
            if qa_key:
                answer = qa_entry["answer"]
                logger.info(f"  -> Found static answer in QA Bank ({qa_key}): '{answer}'")
                success = await self.fill_element(page, field, answer, label_text)
                if success:
                    continue
                    
            # B. Second try dynamic/STAR bank
            star_key, star_entry = self.fuzzy_match(label_text, self.star_bank)
            if star_key:
                entry_type = star_entry.get("type", "static")
                if entry_type == "static":
                    answer = star_entry["answer"]
                    logger.info(f"  -> Found static STAR answer ({star_key}): '{answer}'")
                    success = await self.fill_element(page, field, answer, label_text)
                    if success:
                        continue
                else:
                    # Gemini/NIM generated
                    template = star_entry.get("template", "")
                    logger.info(f"  -> Generating dynamic answer using NIM model for '{star_key}'...")
                    
                    # Generate and strip HTML from raw JD
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(job.raw_jd or "", "html.parser")
                    clean_jd = soup.get_text(separator="\n")
                    
                    answer = self.generate_answer_via_llm(template, label_text, job.company, job.title, clean_jd)
                    
                    if answer:
                        logger.info(f"  -> Generated answer: '{answer}'")
                        success = await self.fill_element(page, field, answer, label_text)
                        if success:
                            # Self-learning: save the newly generated answer back to qa_bank for future reference
                            new_qa_key = f"{job.company.lower()}_{star_key}"
                            self.qa_bank[new_qa_key] = {
                                "answer": answer,
                                "type": "text",
                                "keywords": [label_text.lower(), f"{star_key} at {job.company.lower()}"]
                            }
                            self._save_bank(self.qa_bank, self.qa_bank_path)
                            logger.info(f"  -> Self-learned and saved answer to QA Bank under key '{new_qa_key}'!")
                            continue
                            
            # C. No match found -> highlight the field in yellow for human review
            logger.warning(f"  -> ⚠️ Unknown field: '{label_text}' - highlighting yellow for manual action.")
            try:
                # Set yellow background color and border
                await field.evaluate("el => { el.style.backgroundColor = '#fff3cd'; el.style.border = '2px solid #ffc107'; }")
            except Exception as e:
                logger.debug(f"Failed to style element: {e}")
