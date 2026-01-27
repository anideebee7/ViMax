"""
Fetcher for Google Trends RSS feed.
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from datetime import datetime
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class GoogleTrendsFetcher:
    """Fetches trending topics from Google Trends RSS feed."""

    def __init__(self, rate_limiter=None):
        """
        Initialize the Google Trends fetcher.

        Args:
            rate_limiter: Optional RateLimiter instance for rate limiting
        """
        self.rate_limiter = rate_limiter
        self.base_url = "https://trends.google.com/trending/rss"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_trends(self) -> List[Dict]:
        """
        Fetch trending topics from Google Trends RSS.

        Returns:
            List of dictionaries with keys: title, link, pubDate
        """
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        try:
            async with aiohttp.ClientSession() as session:
                logger.info("Fetching Google Trends RSS feed...")
                async with session.get(self.base_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to fetch Google Trends: HTTP {response.status}")
                    
                    text = await response.text()
                    
                    # Parse RSS XML
                    root = ET.fromstring(text)
                    items = []
                    
                    # RSS format: <item><title>...</title><link>...</link><pubDate>...</pubDate></item>
                    for item in root.findall('.//item'):
                        title_elem = item.find('title')
                        link_elem = item.find('link')
                        pub_date_elem = item.find('pubDate')
                        
                        if title_elem is not None:
                            items.append({
                                'title': title_elem.text or '',
                                'link': link_elem.text if link_elem is not None else '',
                                'pubDate': pub_date_elem.text if pub_date_elem is not None else None
                            })
                    
                    logger.info(f"Fetched {len(items)} trending topics from Google Trends")
                    return items
                    
        except Exception as e:
            logger.error(f"Error fetching Google Trends: {e}")
            raise
