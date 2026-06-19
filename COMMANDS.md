# Scout Auto-Applier CLI Commands

This document contains all the commands you can run using the `scout.bat` CLI.

## 1. Master Pipeline

**Command:** `.\scout.bat pipeline --company <slug>`
**Description:** Runs the entire end-to-end pipeline (Scrape → Score → Tailor → Package). If you provide a company slug (e.g. `retool`), it isolates the entire process to _only_ that company to save API quota.

**Command:** `.\scout.bat process --job <id>`
**Description:** Runs the pipeline for a single specific job (Score → Tailor → Package). It only proceeds to tailoring and packaging if the job scores >= 3.5. Ideal for evaluating a single JD without scraping.

## 2. Scraping

**Command:** `.\scout.bat scrape`
**Description:** Scrapes jobs from all predefined companies in your `config.py` targets (excludes Apify aggregator sources by default).

**Command:** `.\scout.bat scrape --all`
**Description:** Scrapes jobs from all predefined target companies AND runs the Apify aggregator sources (YC and Wellfound) in one command.

**Command:** `.\scout.bat scrape --company <slug>`
**Description:** Scrapes jobs for a specific company (e.g. `retool`, `anthropic`).

**Command:** `.\scout.bat scrape --source <source>`
**Description:** Scrapes jobs for a specific source integration (e.g. `workday`, `yc`, `wellfound`, `direct`).

**Command:** `.\scout.bat scrape --query "Python Backend Engineer"`
**Description:** Uses the Apify integration to scrape LinkedIn jobs based on a specific search query.

## 3. Scoring

**Command:** `.\scout.bat score`
**Description:** Evaluates and scores _all_ unscored jobs currently in the database.

**Command:** `.\scout.bat score --job <id>`
**Description:** Scores one specific job by its ID.

**Command:** `.\scout.bat score --dry-run`
**Description:** Prints out which jobs _would_ be scored without actually calling Gemini, saving your API quota.

## 4. Tailoring & Packaging (Manual Overrides)

**Command:** `.\scout.bat tailor --job <id>`
**Description:** Manually generates a tailored Resume and Cover Letter for a specific job (stored in the database).

**Command:** `.\scout.bat package --job <id>`
**Description:** Manually converts the tailored resume for a specific job into a final PDF in the `output/` folder.

**Command:** `.\scout.bat validate --job <id>`
**Description:** Re-renders a tailored resume PDF to verify its page-fill consistency and page count. It reports the PDF path, page fill percentage (initial and final after scaling), and the actual page count. This helps detect if the content is underfilled, overfilled, or heavily squished, providing warnings and suggestions for improvement.

**Command:** `.\scout.bat validate`
**Description:** Lists all jobs that have a tailored resume and prints each Job ID and its `page_fill` percentage as measured by the renderer (no side-effects or template edits).

**Command:** `.\scout.bat validate --job <id> --increaseline <float>`
**Description:** Performs a single per-render attempt to increase the CSS `--line-height` by the given amount for the specified job and reports the resulting `page_fill`. This is a per-render override only and does not modify `templates/resume.html`.

**Command:** `.\scout.bat validate --job <id> --decreaseline <float>`
**Description:** Performs a single per-render attempt to decrease the CSS `--line-height` by the given amount for the specified job and reports the resulting `page_fill`. This is a per-render override only and does not modify `templates/resume.html`.

## 5. Dashboard & Review

**Command:** `.\scout.bat status`
**Description:** Prints a visual dashboard showing exactly how many jobs are scraped, scored, advanced, and applied.

**Command:** `.\scout.bat review`
**Description:** Lists all application packages that are `ready` to apply. Provides the Job ID, Company, Score, and exact path to the generated PDF.

## 6. Tracking

**Command:** `.\scout.bat mark --job <id> --status applied`
**Description:** Updates the status of an application in your database.
_Valid statuses:_ `ready`, `applied`, `followed_up`, `responded`, `rejected`, `offer`

## 7. Outreach (Cold Emailing)

**Command:** `.\scout.bat outreach --job <job_id> --linkedin <url> --email <addr>`
**Description:** Generates a personalized cold-email draft for the specified job and contact. When you pass `--job` together with `--linkedin` and `--email`, Scout composes a tailored outreach message using the job context and your resume summary; if an SMTP/Gmail sender is configured, it can also send the message. This command is intended for one-off, manual outreach to a found contact.

**Command:** `.\scout.bat outreach --review`
**Description:** Lists saved outreach drafts and generated messages for review. Useful to verify content before sending.

**Command:** `.\scout.bat outreach --mark --job <job_id> --status <status>`
**Description:** Marks an outreach record for the job with a new status (e.g. `sent`, `replied`, `pending`). Useful for tracking follow-ups.

**Notes:**

- The outreach feature requires `data/resume.json` for personalization context. Ensure your contact and API/sender credentials are configured if you expect automated sending.
- Drafts are saved under `output/outreach/` (if enabled) or printed to the console for manual copy-paste.

## 7. Auto-Filling

**Command:** `.\scout.bat apply`
**Description:** Launches a headful browser session and opens every job package marked as `ready` in its own browser tab. Autofills your contact details, uploads your tailored PDF resume, and pastes your cover letter, then pauses for your final submission.

**Command:** `.\scout.bat apply --job <id>`
**Description:** Autofills the application form for a specific job ID, regardless of its status.

## 8. Custom Q&A Bank Management

**Command:** `.\scout.bat qa --list`
**Description:** Lists all standard and open-ended/STAR answers currently stored in the local banks.

**Command:** `.\scout.bat qa --add`
**Description:** Starts an interactive shell utility to add new static fields/demographics to the QA bank.

**Command:** `.\scout.bat qa --edit <key>`
**Description:** Edits the answer or keywords for a specific entry in either the QA bank or STAR bank.
