"""
Fetcher for YouTube Most Popular videos (US region).
"""
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class YouTubeTrendsFetcher:
    """Fetches trending videos from YouTube Most Popular API."""

    def __init__(self, api_key: str, rate_limiter=None, max_results: int = 25):
        """
        Initialize the YouTube Trends fetcher.

        Args:
            api_key: YouTube Data API v3 key
            rate_limiter: Optional RateLimiter instance for rate limiting
            max_results: Maximum number of videos to fetch (default: 25)
        """
        self.api_key = api_key
        self.rate_limiter = rate_limiter
        self.max_results = max_results
        self.base_url = "https://www.googleapis.com/youtube/v3/videos"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_trending(self) -> List[Dict]:
        """
        Fetch trending videos from YouTube Most Popular (US region).

        Returns:
            List of dictionaries with keys: id, snippet (title, publishedAt), statistics (viewCount)
        """
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        try:
            params = {
                'part': 'snippet,statistics',
                'chart': 'mostPopular',
                'regionCode': 'US',
                'maxResults': self.max_results,
                'key': self.api_key
            }

            async with aiohttp.ClientSession() as session:
                logger.info(f"Fetching YouTube Most Popular videos (max {self.max_results})...")
                async with session.get(self.base_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Failed to fetch YouTube trends: HTTP {response.status} - {error_text}")
                    
                    data = await response.json()
                    
                    items = []
                    for item in data.get('items', []):
                        items.append({
                            'id': item.get('id'),
                            'snippet': {
                                'title': item.get('snippet', {}).get('title', ''),
                                'publishedAt': item.get('snippet', {}).get('publishedAt', '')
                            },
                            'statistics': {
                                'viewCount': item.get('statistics', {}).get('viewCount', '0')
                            }
                        })
                    
                    logger.info(f"Fetched {len(items)} trending videos from YouTube")
                    return items
                    
        except Exception as e:
            logger.error(f"Error fetching YouTube trends: {e}")
            raise
