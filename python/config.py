import os
from pathlib import Path
from dotenv import load_dotenv

# Find and load the root .env file
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

# =====================================================================
# API Keys & Port Configurations
# =====================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NIM_API_KEY = os.getenv("NIM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct")

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
SCRAPPER = os.getenv("SCRAPPER")
PDF_SERVICE_PORT = int(os.getenv("PDF_SERVICE_PORT", "3001"))

YC_ACTOR = os.getenv("YC_SCRAPPER")
YC_CONFIG = {
    "startUrls": [
        # You can customize these URLs. I've set them to target remote Software Engineering / Python jobs.
        "https://www.ycombinator.com/jobs/role/software-engineer?remote=true",
        "https://www.ycombinator.com/jobs/role/software-engineer?job_skills=Python",
    ],
    "proxy": {"useApifyProxy": True},
}

WELLFOUND_ACTOR = os.getenv("WF_SCRAPPER")
WELLFOUND_CONFIG = {
    "keyword": "Software Engineer",
    "location": "united-states",
    "results_wanted": 20,
    "max_pages": 5,
    "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
}

# =====================================================================
# Scoring & Evaluation Configuration
# =====================================================================
EMBEDDING_SIMILARITY_THRESHOLD = 0.60
OVERALL_SCORE_THRESHOLD = 3.5

# =====================================================================
# Target Companies Configuration
# =====================================================================
# A list of dictionary objects defining companies to scrape.
# Format:
# {
#   "name": "Company Name",
#   "slug": "url-slug-or-id",
#   "source": "greenhouse" | "lever" | "ashby"
# }
TARGET_COMPANIES = [
    # ── Greenhouse ────────────────────────────────────────────────────────
    {"name": "Anthropic", "slug": "anthropic", "source": "greenhouse"},
    {"name": "Vercel", "slug": "vercel", "source": "greenhouse"},
    {"name": "Figma", "slug": "figma", "source": "greenhouse"},
    {"name": "Gusto", "slug": "gusto", "source": "greenhouse"},
    {"name": "Scale AI", "slug": "scaleai", "source": "greenhouse"},
    {"name": "PagerDuty", "slug": "pagerduty", "source": "greenhouse"},
    {"name": "Reddit", "slug": "reddit", "source": "greenhouse"},
    {"name": "Postman", "slug": "postman", "source": "greenhouse"},
    {"name": "Temporal", "slug": "temporal", "source": "greenhouse"},
    # NOTE: Tome shut down April 2025 — removed
    # NOTE: Coda acquired by Grammarly/Superhuman Dec 2024 — removed
    # NOTE: Rippling uses proprietary ATS — no public API; removed
    # NOTE: Multi acquired by Figma — removed
    # ── Lever ─────────────────────────────────────────────────────────────
    {
        "name": "Octane AI",
        "slug": "octane-ai",
        "source": "lever",
    },  # correct slug (not octaneai)
    # ── Ashby ─────────────────────────────────────────────────────────────
    {"name": "Warp", "slug": "warp", "source": "ashby"},
    {"name": "Vantage", "slug": "vantage", "source": "ashby"},
    {"name": "Linear", "slug": "linear", "source": "ashby"},
    {"name": "Sentry", "slug": "sentry", "source": "ashby"},
    {
        "name": "OneSignal",
        "slug": "onesignal",
        "source": "ashby",
    },  # moved from Greenhouse
    {"name": "Retool", "slug": "retool", "source": "ashby"},  # moved from Greenhouse
    {"name": "Coder", "slug": "coder", "source": "ashby"},  # moved from Lever
    # ── Workday ───────────────────────────────────────────────────────────
    # Format: tenant.wd{N}.myworkdayjobs.com  →  board
    {
        "name": "Salesforce",
        "slug": "salesforce",
        "board": "Salesforce_External_Career_Site",
        "wd": "wd3",
        "source": "workday",
    },
    {
        "name": "Adobe",
        "slug": "adobe",
        "board": "external_experienced",
        "wd": "wd5",
        "source": "workday",
    },
    {
        "name": "Okta",
        "slug": "okta",
        "board": "External_Career_Site",
        "wd": "wd1",
        "source": "workday",
    },
    {
        "name": "Cisco/Splunk",
        "slug": "cisco",
        "board": "External_Career_Site",
        "wd": "wd1",
        "source": "workday",
    },
    {
        "name": "Netflix",
        "slug": "netflix",
        "board": "Netflix_External",
        "wd": "wd1",
        "source": "workday",
    },
    {
        "name": "LinkedIn",
        "slug": "linkedin",
        "board": "External_Career_Site",
        "wd": "wd1",
        "source": "workday",
    },
    {
        "name": "Zalando",
        "slug": "zalando",
        "board": "External_Career_Site",
        "wd": "wd3",
        "source": "workday",
    },
    {
        "name": "Zillow",
        "slug": "zillow",
        "board": "Zillow_External",
        "wd": "wd5",
        "source": "workday",
    },
    {
        "name": "Indeed",
        "slug": "indeed",
        "board": "Indeed_External",
        "wd": "wd5",
        "source": "workday",
    },
    # ── SmartRecruiters ───────────────────────────────────────────────────
    {"name": "Delivery Hero", "slug": "DeliveryHero", "source": "smartrecruiters"},
    # NOTE: Booking.com — proprietary Phenom People ATS, no public API; removed
    # NOTE: Twitter/X — internal proprietary ATS, no public API; removed
    # ── Direct (Playwright) ───────────────────────────────────────────────
    {"name": "Notion", "slug": "notion", "source": "direct"},
    {"name": "Supabase", "slug": "supabase", "source": "direct"},
    {"name": "Stripe", "slug": "stripe", "source": "direct"},
    {"name": "Rippling", "slug": "rippling", "source": "direct"},
]

# =====================================================================
# Filtering Keywords
# =====================================================================
# These can be used for initial lightweight pattern-matching before full LLM evaluation
KEYWORD_FILTERS = [
    "python",
    "fastapi",
    "backend",
    "django",
    "flask",
    "platform",
    "infrastructure",
    "software engineer",
    "database",
]

# Auto-reject patterns (roles that we immediately ignore)
REJECT_TITLE_PATTERNS = [
    "frontend",
    "react",
    "vue",
    "angular",
    "ui/ux",
    "designer",
    "qa",
    "test",
    "quality assurance",
    "devops",
    "security clearance",
    "lead",
    "principal",
    "manager",
    "director",
    "vp",
    "staff",
]
