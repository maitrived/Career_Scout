from apify_client import ApifyClient
import os
import logging

logger = logging.getLogger(__name__)

ACTOR_ID = "datadoping/linkedin-profile-scraper"

async def scrape_profile(linkedin_url: str) -> dict | None:
    client = ApifyClient(os.getenv("APIFY_API_TOKEN"))
    
    logger.info(f"Calling Apify actor {ACTOR_ID} for {linkedin_url}")
    
    run = client.actor(ACTOR_ID).call(run_input={
        "profiles": [linkedin_url]
    })
    
    if not run or "defaultDatasetId" not in run:
        logger.warning(f"Apify actor failed or returned no dataset. Run object: {run}")
        return None
        
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    return items[0] if items else None
