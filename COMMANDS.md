# Scout Auto-Applier CLI Commands

This document contains all the commands you can run using the `scout.bat` CLI.

## 1. Master Pipeline
**Command:** `.\scout.bat pipeline --company <slug>`
**Description:** Runs the entire end-to-end pipeline (Scrape → Score → Tailor → Package). If you provide a company slug (e.g. `retool`), it isolates the entire process to *only* that company to save API quota.

**Command:** `.\scout.bat process --job <id>`
**Description:** Runs the pipeline for a single specific job (Score → Tailor → Package). It only proceeds to tailoring and packaging if the job scores >= 3.5. Ideal for evaluating a single JD without scraping.

## 2. Scraping
**Command:** `.\scout.bat scrape`
**Description:** Scrapes jobs from all predefined companies in your `config.py` targets.

**Command:** `.\scout.bat scrape --company <slug>`
**Description:** Scrapes jobs for a specific company (e.g. `retool`, `anthropic`).

**Command:** `.\scout.bat scrape --query "Python Backend Engineer"`
**Description:** Uses the Apify integration to scrape LinkedIn jobs based on a specific search query.

## 3. Scoring
**Command:** `.\scout.bat score`
**Description:** Evaluates and scores *all* unscored jobs currently in the database.

**Command:** `.\scout.bat score --job <id>`
**Description:** Scores one specific job by its ID.

**Command:** `.\scout.bat score --dry-run`
**Description:** Prints out which jobs *would* be scored without actually calling Gemini, saving your API quota.

## 4. Tailoring & Packaging (Manual Overrides)
**Command:** `.\scout.bat tailor --job <id>`
**Description:** Manually generates a tailored Resume and Cover Letter for a specific job (stored in the database).

**Command:** `.\scout.bat package --job <id>`
**Description:** Manually converts the tailored resume for a specific job into a final PDF in the `output/` folder.

## 5. Dashboard & Review
**Command:** `.\scout.bat status`
**Description:** Prints a visual dashboard showing exactly how many jobs are scraped, scored, advanced, and applied.

**Command:** `.\scout.bat review`
**Description:** Lists all application packages that are `ready` to apply. Provides the Job ID, Company, Score, and exact path to the generated PDF.

## 6. Tracking
**Command:** `.\scout.bat mark --job <id> --status applied`
**Description:** Updates the status of an application in your database. 
*Valid statuses:* `ready`, `applied`, `followed_up`, `responded`, `rejected`, `offer`

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
