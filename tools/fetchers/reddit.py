"""
Fetcher for Reddit hot posts from health-related subreddits.
"""
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class RedditFetcher:
    """Fetches hot posts from Reddit health subreddits."""

    # Default health subreddits
    DEFAULT_SUBREDDITS = [
        'nutrition',
        'Fitness',
        'Biohackers',
        'Supplements',
        'Longevity',
        'loseit'
    ]

    def __init__(self, rate_limiter=None, subreddits: Optional[List[str]] = None, limit: int = 25):
        """
        Initialize the Reddit fetcher.

        Args:
            rate_limiter: Optional RateLimiter instance for rate limiting
            subreddits: List of subreddit names (default: DEFAULT_SUBREDDITS)
            limit: Number of posts per subreddit (default: 25, max: 100)
        """
        self.rate_limiter = rate_limiter
        self.subreddits = subreddits or self.DEFAULT_SUBREDDITS
        self.limit = min(limit, 100)  # Reddit max is 100
        self.base_url = "https://www.reddit.com"
        self.user_agent = "IntelliVerseHealthBot/1.0"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_subreddit_hot(self, subreddit: str) -> List[Dict]:
        """
        Fetch hot posts from a specific subreddit.

        Args:
            subreddit: Subreddit name (without r/)

        Returns:
            List of dictionaries with keys: title, url, created_utc, ups, subreddit
        """
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        url = f"{self.base_url}/r/{subreddit}/hot.json"
        params = {'limit': self.limit}
        headers = {'User-Agent': self.user_agent}

        try:
            async with aiohttp.ClientSession() as session:
                logger.info(f"Fetching hot posts from r/{subreddit}...")
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Failed to fetch r/{subreddit}: HTTP {response.status} - {error_text}")
                    
                    data = await response.json()
                    
                    items = []
                    for child in data.get('data', {}).get('children', []):
                        post_data = child.get('data', {})
                        items.append({
                            'title': post_data.get('title', ''),
                            'url': post_data.get('url', ''),
                            'created_utc': post_data.get('created_utc', 0),
                            'ups': post_data.get('ups', 0),
                            'subreddit': post_data.get('subreddit', subreddit)
                        })
                    
                    logger.info(f"Fetched {len(items)} posts from r/{subreddit}")
                    return items
                    
        except Exception as e:
            logger.error(f"Error fetching r/{subreddit}: {e}")
            raise

    async def fetch_all_subreddits(self) -> List[Dict]:
        """
        Fetch hot posts from all configured subreddits in parallel.

        Returns:
            Flattened list of all posts from all subreddits
        """
        logger.info(f"Fetching from {len(self.subreddits)} subreddits: {', '.join(self.subreddits)}")
        
        tasks = [self.fetch_subreddit_hot(subreddit) for subreddit in self.subreddits]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_items = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch r/{self.subreddits[i]}: {result}")
            else:
                all_items.extend(result)
        
        logger.info(f"Total fetched: {len(all_items)} posts from all subreddits")
        return all_items
