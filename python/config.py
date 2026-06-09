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
    {"name": "DV Trading", "slug": "dvtrading", "source": "greenhouse"},
    {"name": "Pilot HQ", "slug": "pilothq", "source": "greenhouse"},
    {"name": "Clover Health", "slug": "cloverhealth", "source": "greenhouse"},
    # User-added Greenhouse companies
    {"name": "Together AI", "slug": "togetherai", "source": "greenhouse"},
    {"name": "Mixpanel", "slug": "mixpanel", "source": "greenhouse"},
    {"name": "Amplitude", "slug": "amplitude", "source": "greenhouse"},
    {"name": "Brex", "slug": "brex", "source": "greenhouse"},
    {"name": "Tanium", "slug": "tanium", "source": "greenhouse"},
    {"name": "Flexport", "slug": "flexport", "source": "greenhouse"},
    {"name": "project44", "slug": "project44", "source": "greenhouse"},
    {"name": "Salsify", "slug": "salsify", "source": "greenhouse"},
    {"name": "Coinbase", "slug": "coinbase", "source": "greenhouse"},
    {"name": "Robinhood", "slug": "robinhood", "source": "greenhouse"},
    {"name": "Lyft", "slug": "lyft", "source": "greenhouse"},
    {"name": "Instacart", "slug": "instacart", "source": "greenhouse"},
    {"name": "Waymo", "slug": "waymo", "source": "greenhouse"},
    {"name": "Dropbox", "slug": "dropbox", "source": "greenhouse"},
    {"name": "Twitch", "slug": "twitch", "source": "greenhouse"},
    {"name": "Intercom", "slug": "intercom", "source": "greenhouse"},
    {"name": "Klaviyo", "slug": "klaviyo", "source": "greenhouse"},
    {"name": "Contentful", "slug": "contentful", "source": "greenhouse"},
    {"name": "Typeform", "slug": "typeform", "source": "greenhouse"},
    {"name": "Airtable", "slug": "airtable", "source": "greenhouse"},
    {"name": "Duolingo", "slug": "duolingo", "source": "greenhouse"},
    {"name": "Coursera", "slug": "coursera", "source": "greenhouse"},
    {"name": "Oscar", "slug": "oscar", "source": "greenhouse"},
    {"name": "Carta", "slug": "carta", "source": "greenhouse"},
    {"name": "Remote", "slug": "remote", "source": "greenhouse"},
    {"name": "Lattice", "slug": "lattice", "source": "greenhouse"},
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
    {"name": "WHOOP", "slug": "whoop", "source": "lever"},
    {"name": "Arrive Logistics", "slug": "arrivelogistics", "source": "lever"},
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
    {"name": "Pylon Labs", "slug": "pylon-labs", "source": "ashby"},
    {"name": "Nooks", "slug": "nooks", "source": "ashby"},
    {"name": "Northwood Space", "slug": "NorthwoodSpace", "source": "ashby"},
    {"name": "Compa", "slug": "compa", "source": "ashby"},
    {"name": "Authorium", "slug": "Authorium", "source": "ashby"},
    {"name": "Chalk", "slug": "chalk", "source": "ashby"},
    {"name": "OpenAI", "slug": "openai", "source": "ashby"},
    {"name": "Tessera Labs", "slug": "tessera-labs", "source": "ashby"},
    {"name": "Stainless API", "slug": "stainlessapi", "source": "ashby"},
    {"name": "Distyl", "slug": "Distyl", "source": "ashby"},
    {"name": "Rillet", "slug": "rillet", "source": "ashby"},
    {"name": "Column", "slug": "column", "source": "ashby"},
    {"name": "Zip", "slug": "zip", "source": "ashby"},
    {"name": "1Password", "slug": "1password", "source": "ashby"},
    {"name": "Heliux", "slug": "heliux", "source": "ashby"},
    {"name": "Lambda Labs", "slug": "Lambda", "source": "ashby"},
    {"name": "Scribe", "slug": "scribe", "source": "ashby"},
    {"name": "Render", "slug": "render", "source": "ashby"},
    {"name": "Notion", "slug": "notion", "source": "ashby"},
    # ── Workday ───────────────────────────────────────────────────────────
    # Format: tenant.wd{N}.myworkdayjobs.com  →  board
    {
        "name": "Salesforce",
        "slug": "salesforce",
        "board": "External_Career_Site",
        "wd": "wd12",
        "source": "workday",
    },
    {
        "name": "Nvidia",
        "slug": "nvidia",
        "board": "NVIDIAExternalCareerSite",
        "wd": "wd5",
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
    {
        "name": "WGU",
        "slug": "wgu",
        "board": "External",
        "wd": "wd5",
        "source": "workday",
    },
    {
        "name": "Microchip",
        "slug": "microchiphr",
        "board": "External",
        "wd": "wd5",
        "source": "workday",
    },
    {
        "name": "OCLC",
        "slug": "oclc",
        "board": "OCLC_Careers",
        "wd": "wd1",
        "source": "workday",
    },
    {
        "name": "Visa",
        "slug": "visa",
        "board": "Visa",
        "wd": "wd5",
        "source": "workday",
    },
    {
        "name": "Autodesk",
        "slug": "autodesk",
        "board": "Ext",
        "wd": "wd1",
        "source": "workday",
    },
    {
        "name": "Univision",
        "slug": "univision",
        "board": "External",
        "wd": "wd1",
        "source": "workday",
    },
    # ── SmartRecruiters ───────────────────────────────────────────────────
    {"name": "Delivery Hero", "slug": "DeliveryHero", "source": "smartrecruiters"},
    # NOTE: Booking.com — proprietary Phenom People ATS, no public API; removed
    # NOTE: Twitter/X — internal proprietary ATS, no public API; removed
    # ── Direct (Playwright) ───────────────────────────────────────────────
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
