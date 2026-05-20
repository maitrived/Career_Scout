import os
from pathlib import Path
from dotenv import load_dotenv

# Find and load the root .env file
dotenv_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

# =====================================================================
# API Keys & Port Configurations
# =====================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NIM_API_KEY = os.getenv("NIM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct")

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
SCRAPPER = os.getenv("SCRAPPER", "curious_coder/linkedin-jobs-scraper")
PDF_SERVICE_PORT = int(os.getenv("PDF_SERVICE_PORT", "3001"))

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
    # Greenhouse companies
    {"name": "Anthropic", "slug": "anthropic", "source": "greenhouse"},
    {"name": "Retool", "slug": "retool", "source": "greenhouse"},
    {"name": "Linear", "slug": "linear", "source": "greenhouse"},
    {"name": "Vercel", "slug": "vercel", "source": "greenhouse"},
    {"name": "Figma", "slug": "figma", "source": "greenhouse"},
    {"name": "Rippling", "slug": "rippling", "source": "greenhouse"},
    {"name": "Gusto", "slug": "gusto", "source": "greenhouse"},
    {"name": "Tome", "slug": "tome", "source": "greenhouse"},
    {"name": "Octane AI", "slug": "octaneai", "source": "greenhouse"},
    {"name": "Sentry", "slug": "sentry", "source": "greenhouse"},
    {"name": "Scale AI", "slug": "scaleai", "source": "greenhouse"},
    
    # Lever companies
    {"name": "Figma Lever", "slug": "figma", "source": "lever"},
    {"name": "Postman", "slug": "postman", "source": "lever"},
    {"name": "Coder", "slug": "coder", "source": "lever"},
    {"name": "Lob", "slug": "lob", "source": "lever"},
    {"name": "Temporal", "slug": "temporal", "source": "lever"},
    {"name": "Coda", "slug": "coda", "source": "lever"},
    {"name": "Retool Lever", "slug": "retool", "source": "lever"},
    
    # Ashby companies
    {"name": "Warp", "slug": "warp", "source": "ashby"},
    {"name": "Multi", "slug": "multi", "source": "ashby"},
    {"name": "OneSignal", "slug": "onesignal", "source": "ashby"},
    {"name": "Vantage", "slug": "vantage", "source": "ashby"},
]

# =====================================================================
# Filtering Keywords
# =====================================================================
# These can be used for initial lightweight pattern-matching before full LLM evaluation
KEYWORD_FILTERS = [
    "python", "fastapi", "backend", "django", "flask", 
    "platform", "infrastructure", "software engineer", "database"
]

# Auto-reject patterns (roles that we immediately ignore)
REJECT_TITLE_PATTERNS = [
    "frontend", "react", "vue", "angular", "ui/ux", "designer", 
    "qa", "test", "quality assurance", "devops", "security clearance",
    "lead", "principal", "manager", "director", "vp", "staff"
]
