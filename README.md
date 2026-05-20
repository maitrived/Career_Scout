# Scout Auto‑Applier

A **Python + TypeScript** pipeline that scrapes job postings, scores them against your profile, tailors a résumé & cover‑letter, and generates a ready‑to‑apply PDF package.

## Quick Start
```bash
# Clone the repo
git clone <repo‑url>
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
| Phase | Command | What it does |
|------|---------|--------------|
| 1️⃣  | `scout.bat scrape` | Pull jobs from Greenhouse, Lever, Ashby, LinkedIn, etc. |
| 2️⃣  | `scout.bat score`   | Score each job (only keep `overall_score ≥ 3.5`). |
| 3️⃣  | `scout.bat tailor --job <id>` | Generate a tailored résumé & cover‑letter (stored in the DB). |
| 4️⃣  | `scout.bat package --job <id>` | Render a PDF via Playwright (see `ts/`). |
| 5️⃣  | `scout.bat apply`   | Open a headful Chrome window with one tab per **ready** application; the tool autofills your details but **does not submit** – you review and click Submit manually. |

## Privacy – Do Not Commit Personal Data
* `data/resume.json` and `data/resume.md` contain your contact information. They are listed in **`.gitignore`** and will never be committed.
* A template (`data/resume.example.json` / `data/resume.example.md`) is provided so others can add their own data without exposing yours.
* `.env` files with API keys are also ignored by default.

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
*This repository is intended for personal job‑search automation. **Never enable auto‑submit** – the human must review each application.*
