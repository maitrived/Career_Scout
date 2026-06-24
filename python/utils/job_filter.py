import re
from typing import List
from python.db.models import Job
import json
from pathlib import Path


# Load candidate preferences (willing_to_relocate) once at import time
_WILLING_TO_RELOCATE = False
try:
    resume_path = Path("data/resume.json")
    if not resume_path.exists():
        resume_path = Path(__file__).resolve().parent.parent / "data" / "resume.json"
    if resume_path.exists():
        data = json.loads(resume_path.read_text(encoding="utf-8"))
        _WILLING_TO_RELOCATE = bool(data.get("willing_to_relocate", False))
except Exception:
    _WILLING_TO_RELOCATE = False

# Roles to accept
ALLOWED_ROLES = [
    r"software", r"engineer", r"developer", r"ai\b", r"machine learning",
    r"backend", r"fullstack", r"full-stack", r"full stack", r"forward deployed",
    r"platform", r"infrastructure", r"data"
]

# Roles to reject explicitly
BLOCKED_ROLES = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b", r"\bmanager\b",
    r"\bdirector\b", r"\bvp\b", r"\bhead\b", r"\baccount executive\b", r"\bsales\b",
    r"\bhr\b", r"\bstaff\b", r"\bmarketing\b", r"\bproduct manager\b", r"\bfounder\b"
]

# Locations to accept (plus 'remote' handled globally)
ALLOWED_LOCATIONS = [
    r"\bus\b", r"\busa\b", r"\bunited states\b", r"\bindia\b", r"\bremote\b",
    # Major US tech hubs/states for safety
    r"\bca\b", r"\bcalifornia\b", r"\bny\b", r"\bnew york\b", r"\bwa\b", r"\bwashington\b",
    r"\btx\b", r"\btexas\b", r"\baz\b", r"\barizona\b", r"\bil\b", r"\billinois\b",
    r"\bco\b", r"\bcolorado\b", r"\bma\b", r"\bmassachusetts\b",
    # Major cities that might appear without states
    r"\bsan jose\b", r"\bsan francisco\b", r"\bsf\b", r"\bseattle\b", r"\baustin\b",
    r"\bnyc\b", r"\bboston\b", r"\bchicago\b", r"\bdenver\b", r"\batlanta\b",
    r"\blos angeles\b", r"\bla\b", r"\bsan diego\b", r"\bdallas\b", r"\bh Houston\b"
]

def passes_job_filter(job: Job) -> bool:
    """
    Evaluates a job against role and location criteria.
    Returns True if it's a junior/mid-level IT job in the US or India.
    """
    title = job.title.lower()
    location = str(job.location).lower() if job.location else ""
    
    # 1. Check blocked roles
    for block_pattern in BLOCKED_ROLES:
        if re.search(block_pattern, title):
            return False
            
    # 2. Check allowed roles
    role_match = False
    for allow_pattern in ALLOWED_ROLES:
        if re.search(allow_pattern, title):
            role_match = True
            break
            
    if not role_match:
        return False
    # If the candidate is willing to relocate anywhere, accept based on role only
    if _WILLING_TO_RELOCATE:
        return True
        
    # 3. Check location (Must be remote, US, or India)
    if job.remote:
        return True # Explicit remote flag
        
    loc_match = False
    for loc_pattern in ALLOWED_LOCATIONS:
        if re.search(loc_pattern, location) or re.search(loc_pattern, title):
            loc_match = True
            break
            
    # If location explicitly states remote in string, accept it
    if "remote" in location or "anywhere" in location:
        loc_match = True
        
    if not loc_match:
        return False
        
    return True
