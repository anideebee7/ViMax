"""
Fetcher for NewsAPI top headlines (health category).
"""
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class NewsAPIFetcher:
    """Fetches top headlines from NewsAPI (health category)."""

    def __init__(self, api_key: str, rate_limiter=None, page_size: int = 50):
        """
        Initialize the NewsAPI fetcher.

        Args:
            api_key: NewsAPI API key
            rate_limiter: Optional RateLimiter instance for rate limiting
            page_size: Number of articles to fetch (default: 50, max: 100)
        """
        self.api_key = api_key
        self.rate_limiter = rate_limiter
        self.page_size = min(page_size, 100)  # NewsAPI max is 100
        self.base_url = "https://newsapi.org/v2/top-headlines"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_health_headlines(self) -> List[Dict]:
        """
        Fetch top health headlines from NewsAPI (US).

        Returns:
            List of dictionaries with keys: title, url, publishedAt, source (name)
        """
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        try:
            params = {
                'country': 'us',
                'category': 'health',
                'pageSize': self.page_size
            }
            headers = {
                'X-Api-Key': self.api_key
            }

            async with aiohttp.ClientSession() as session:
                logger.info(f"Fetching NewsAPI health headlines (max {self.page_size})...")
                async with session.get(
                    self.base_url, 
                    params=params, 
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Failed to fetch NewsAPI: HTTP {response.status} - {error_text}")
                    
                    data = await response.json()
                    
                    if data.get('status') != 'ok':
                        raise Exception(f"NewsAPI returned error: {data.get('message', 'Unknown error')}")
                    
                    items = []
                    for article in data.get('articles', []):
                        items.append({
                            'title': article.get('title', ''),
                            'url': article.get('url', ''),
                            'publishedAt': article.get('publishedAt', ''),
                            'source': {
                                'name': article.get('source', {}).get('name', '')
                            }
                        })
                    
                    logger.info(f"Fetched {len(items)} health headlines from NewsAPI")
                    return items
                    
        except Exception as e:
            logger.error(f"Error fetching NewsAPI headlines: {e}")
            raise
