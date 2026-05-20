from abc import ABC, abstractmethod
from typing import List, Dict, Any
from python.db.models import Job

class BaseScraper(ABC):
    """
    Abstract base class for all scrapers (Greenhouse, Lever, Apify, etc.)
    """

    @abstractmethod
    async def fetch_jobs(self, target: str) -> List[Job]:
        """
        Fetches job postings for a given target company or query and returns a list of normalized Job models.
        
        Args:
            target: The company slug/ID or query term to fetch postings for.
            
        Returns:
            A list of Pydantic Job models.
        """
        pass

    @abstractmethod
    def normalize(self, raw: Dict[str, Any], company: str) -> Job:
        """
        Transforms raw scraping output into a structured Pydantic Job model.
        
        Args:
            raw: Raw dictionary representing the job posting from the source API or scraper.
            company: The name or slug of the company.
            
        Returns:
            A normalized Pydantic Job model.
        """
        pass
