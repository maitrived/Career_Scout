import os
import json
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
        for key, entry in bank.items():
            keywords = entry.get("keywords", [])
            for kw in keywords:
                if kw.lower() in label_lower:
                    return key, entry
        return None, None

    async def get_label_text(self, page: Page, element) -> str:
        """Retrieves cleaned label or descriptive text associated with an input element."""
        try:
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
            
            if tag_name == "select":
                # Handle dropdown selection
                options_count = await element.locator("option").count()
                best_val = None
                
                # Check for perfect match or fuzzy keyword match
                for i in range(options_count):
                    opt = element.locator("option").nth(i)
                    opt_text = (await opt.inner_text()).strip()
                    opt_val = await opt.get_attribute("value")
                    
                    if opt_val:
                        if answer.lower() == opt_text.lower():
                            best_val = opt_val
                            break
                        elif answer.lower() in opt_text.lower():
                            best_val = opt_val
                            # keep searching for an exact match, but hold this as fallback
                
                if best_val:
                    await element.select_option(value=best_val)
                    return True
                else:
                    try:
                        await element.select_option(label=answer)
                        return True
                    except Exception:
                        pass
                
            elif tag_name == "input" and type_attr == "radio":
                # Handle radio input: we should click it if its own text/value represents the answer
                # E.g. find label or parent text near the radio input
                radio_text = await element.evaluate("""el => {
                    // Try to find direct label or text sibling
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
                # Handle checkbox
                should_check = answer.lower() in ["yes", "true", "1", "checked", "agree", "y"]
                is_checked = await element.is_checked()
                if should_check != is_checked:
                    await element.click()
                return True
                
            else:
                # Handle standard text input and textareas
                await element.fill(answer)
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
