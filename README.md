# Scout Auto‑Applier

A **Python + TypeScript** pipeline that scrapes job postings, scores them against your profile, tailors a résumé & cover‑letter, and generates a ready‑to‑apply PDF package.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/ParvaChaudhari/Career_Scout.git
cd Scout

# Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
# Install Playwright browsers
python -m playwright install
```

## Workflow

| Phase | Command                        | What it does                                                                                                                                                         |
| ----- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1️⃣    | `scout.bat scrape`             | Pull jobs from Greenhouse, Lever, Ashby, Workday, SmartRecruiters.                                                                                                   |
| 2️⃣    | `scout.bat score`              | Score each job (only keep `overall_score ≥ 3.5`).                                                                                                                    |
| 3️⃣    | `scout.bat tailor --job <id>`  | Generate a tailored résumé & cover‑letter (stored in the DB).                                                                                                        |
| 4️⃣    | `scout.bat package --job <id>` | Render a PDF via Playwright (see `ts/`).                                                                                                                             |
| 5️⃣    | `scout.bat apply`              | Open a headful Chrome window with one tab per **ready** application; the tool autofills your details but **does not submit** – you review and click Submit manually. |

## CLI Commands

Below are the primary CLI commands available via `scout.bat`. See `COMMANDS.md` for a fuller reference.

- `scout.bat pipeline --company <slug>` — Run end-to-end pipeline for a company (Scrape → Score → Tailor → Package).
- `scout.bat process --job <id>` — Run pipeline for a single job (Score → Tailor → Package).
- `scout.bat scrape [--company <slug>] [--query "<text>"] [--source <source>] [--all]` — Scrape jobs globally, for a company, a query, a specific source (like `yc`), or all sources combined.
- `scout.bat score [--job <id>] [--dry-run]` — Score jobs; `--dry-run` prints which jobs would be scored.
- `scout.bat tailor --job <id>` — Generate tailored resume and cover letter for a job and store in DB.
- `scout.bat package --job <id>` — Render tailored resume to PDF in `output/`.
- `scout.bat validate` — List all jobs that have a tailored resume and print each Job ID and its measured `page_fill` (no side-effects).
- `scout.bat validate --job <id>` — Re-render a single job and print PDF path, `initial` and `final` page-fill, and actual page count.
- `scout.bat validate --job <id> --increaseline <float>` — Single per-render attempt to increase CSS `--line-height` by the given amount and report resulting `page_fill`.
- `scout.bat validate --job <id> --decreaseline <float>` — Single per-render attempt to decrease CSS `--line-height` by the given amount and report resulting `page_fill`.
- `scout.bat status` — Show dashboard with scrape/score/tailor/package/apply stats.
- `scout.bat review` — List application packages that are `ready` to apply (Job ID, company, score, PDF path).
- `scout.bat mark --job <id> --status <status>` — Update an application's status (`ready`, `applied`, `followed_up`, `responded`, `rejected`, `offer`).
- `scout.bat apply [--job <id>]` — Headful autofill of application forms; opens one tab per job (does not auto-submit). If `--job` provided, acts on a single package.
- `scout.bat qa --list|--add|--edit <key>` — Manage the Q&A bank (list entries, add new, or edit existing entries).
- `scout.bat outreach --job <job_id> --linkedin <url> --email <addr>` — Generate a personalized cold-email draft for the given job and contact (uses job context and `data/resume.json` for personalization). If --linkedin and --email are provided together, Scout will compose the message and, when an SMTP/Gmail sender is configured, may send it.
- `scout.bat outreach --review` — List saved outreach drafts for review.
- `scout.bat outreach --mark --job <job_id> --status <status>` — Mark an outreach record for tracking follow-ups (e.g. `sent`, `replied`, `pending`).

## Privacy – Do Not Commit Personal Data

- `data/resume.json` and `data/resume.md` contain your contact information. They are listed in **`.gitignore`** and will never be committed.
- A template (`data/resume.example.json` / `data/resume.example.md`) is provided so others can add their own data without exposing yours.
- `.env` files with API keys are also ignored by default.

## Personalization Notice

- **Purpose:** This project and its scoring/tailoring logic are configured for me (Parva) (many inputs — projects, experience, Q&A — are intentionally hard-coded). It is provided as a personal tool and may not work "out of the box" for others.
- **How to adapt:** Replace or edit your personal data in `data/resume.json`, `data/resume.md`, and the example templates in `templates/`. Update or remove any hard-coded entries in `python/tailor/`, `data/qa_bank.json`, and `scorer/` to reflect your own experience.
- **Need help customizing?** Ask an AI agent (for example, open an issue or prompt your assistant with a request like "Help me adapt Scout to my resume: replace Parva's projects and experiences with mine and update scoring rules"). You can also fork the repo and search for occurrences of "Parva" or your own name to find places to edit.

## Generating a New Project

```bash
scout.bat pipeline --company <slug>
```

Runs the full end‑to‑end pipeline for a single company.

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make sure your changes pass the existing tests (`python -m pytest`).
4. Submit a pull request.

---

_This repository is intended for personal job‑search automation. **Never enable auto‑submit** – the human must review each application._
