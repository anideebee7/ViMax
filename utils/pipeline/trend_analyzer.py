"""Trend analyzer utility that aggregates trends from multiple sources."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from interfaces.output.monetization import TrendContext


class TrendAnalyzer:
    """Aggregates and analyzes trends from multiple data sources."""

    def __init__(
        self,
        google_fetcher=None,
        youtube_fetcher=None,
        reddit_fetcher=None,
        newsapi_fetcher=None,
        category_filter: Optional[str] = None,
    ):
        """
        Initialize TrendAnalyzer with optional fetchers.

        Args:
            google_fetcher: GoogleTrendsFetcher instance
            youtube_fetcher: YouTubeTrendsFetcher instance
            reddit_fetcher: RedditFetcher instance
            newsapi_fetcher: NewsAPIFetcher instance
            category_filter: Optional category to filter trends (e.g., 'health', 'tech')
        """
        self.google_fetcher = google_fetcher
        self.youtube_fetcher = youtube_fetcher
        self.reddit_fetcher = reddit_fetcher
        self.newsapi_fetcher = newsapi_fetcher
        self.category_filter = category_filter
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_config(cls, config: dict) -> "TrendAnalyzer":
        """
        Create TrendAnalyzer from configuration dict.

        Config example:
        {
            "google_trends": {"enabled": true},
            "youtube_trends": {"enabled": true, "api_key": "..."},
            "reddit": {"enabled": true, "subreddits": ["technology", "news"]},
            "newsapi": {"enabled": true, "api_key": "..."},
            "category_filter": "technology"
        }
        """
        google_fetcher = None
        youtube_fetcher = None
        reddit_fetcher = None
        newsapi_fetcher = None

        if config.get("google_trends", {}).get("enabled"):
            try:
                from tools.fetchers import GoogleTrendsFetcher

                google_fetcher = GoogleTrendsFetcher()
            except ImportError:
                logging.warning("GoogleTrendsFetcher not available")

        if config.get("youtube_trends", {}).get("enabled"):
            api_key = config["youtube_trends"].get("api_key")
            if api_key:
                try:
                    from tools.fetchers import YouTubeTrendsFetcher

                    youtube_fetcher = YouTubeTrendsFetcher(api_key=api_key)
                except ImportError:
                    logging.warning("YouTubeTrendsFetcher not available")

        if config.get("reddit", {}).get("enabled"):
            try:
                from tools.fetchers import RedditFetcher

                subreddits = config["reddit"].get("subreddits", [])
                reddit_fetcher = RedditFetcher(subreddits=subreddits)
            except ImportError:
                logging.warning("RedditFetcher not available")

        if config.get("newsapi", {}).get("enabled"):
            api_key = config["newsapi"].get("api_key")
            if api_key:
                try:
                    from tools.fetchers import NewsAPIFetcher

                    newsapi_fetcher = NewsAPIFetcher(api_key=api_key)
                except ImportError:
                    logging.warning("NewsAPIFetcher not available")

        return cls(
            google_fetcher=google_fetcher,
            youtube_fetcher=youtube_fetcher,
            reddit_fetcher=reddit_fetcher,
            newsapi_fetcher=newsapi_fetcher,
            category_filter=config.get("category_filter"),
        )

    async def fetch_trends(
        self, category: Optional[str] = None, limit: int = 20
    ) -> TrendContext:
        """
        Fetch trends from all configured sources.

        Args:
            category: Optional category filter (overrides instance category_filter)
            limit: Maximum number of trends per source

        Returns:
            TrendContext with aggregated trend data
        """
        category = category or self.category_filter
        tasks = []
        source_names = []

        if self.google_fetcher:
            tasks.append(self._fetch_google_trends(limit))
            source_names.append("google")

        if self.youtube_fetcher:
            tasks.append(self._fetch_youtube_trends(limit))
            source_names.append("youtube")

        if self.reddit_fetcher:
            tasks.append(self._fetch_reddit_trends(limit))
            source_names.append("reddit")

        if self.newsapi_fetcher:
            tasks.append(self._fetch_news_trends(limit))
            source_names.append("news")

        if not tasks:
            self.logger.warning("No trend fetchers configured")
            return TrendContext(fetched_at=datetime.now(timezone.utc).isoformat())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        all_topics = []
        all_hashtags = []
        news_topics = []
        source_breakdown = {}

        for name, result in zip(source_names, results):
            if isinstance(result, Exception):
                self.logger.warning(f"Failed to fetch {name} trends: {result}")
                continue

            source_breakdown[name] = result
            topics = result.get("topics", [])
            all_topics.extend(topics)

            if name == "news":
                news_topics.extend(topics)

            # Extract hashtags from topics
            for topic in topics:
                if isinstance(topic, str):
                    # Convert topic to hashtag format
                    tag = "#" + "".join(word.capitalize() for word in topic.split()[:3])
                    all_hashtags.append(tag)

        # Deduplicate and limit
        seen_topics = set()
        unique_topics = []
        for topic in all_topics:
            if isinstance(topic, str) and topic.lower() not in seen_topics:
                seen_topics.add(topic.lower())
                unique_topics.append(topic)

        seen_hashtags = set()
        unique_hashtags = []
        for tag in all_hashtags:
            if tag.lower() not in seen_hashtags:
                seen_hashtags.add(tag.lower())
                unique_hashtags.append(tag)

        return TrendContext(
            trending_topics=unique_topics[:limit],
            trending_hashtags=unique_hashtags[:limit],
            trending_sounds=[],  # Would need TikTok API for this
            news_topics=news_topics[:10],
            source_breakdown=source_breakdown,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _fetch_google_trends(self, limit: int) -> Dict[str, Any]:
        """Fetch trends from Google Trends."""
        try:
            # The method name in GoogleTrendsFetcher is fetch_trends
            items = await self.google_fetcher.fetch_trends()
            topics = [item.get("title", "") for item in items[:limit] if item.get("title")]
            return {"topics": topics, "raw": items}
        except Exception as e:
            self.logger.error(f"Google Trends fetch error: {e}")
            return {"topics": [], "raw": [], "error": str(e)}

    async def _fetch_youtube_trends(self, limit: int) -> Dict[str, Any]:
        """Fetch trends from YouTube."""
        try:
            # The method name in YouTubeTrendsFetcher is fetch_trending
            items = await self.youtube_fetcher.fetch_trending()
            topics = [item.get("snippet", {}).get("title", "") for item in items[:limit]]
            return {"topics": topics, "raw": items}
        except Exception as e:
            self.logger.error(f"YouTube Trends fetch error: {e}")
            return {"topics": [], "raw": [], "error": str(e)}

    async def _fetch_reddit_trends(self, limit: int) -> Dict[str, Any]:
        """Fetch trends from Reddit."""
        try:
            # The method name in RedditFetcher is fetch_all_subreddits
            items = await self.reddit_fetcher.fetch_all_subreddits()
            topics = [item.get("title", "") for item in items[:limit] if item.get("title")]
            return {"topics": topics, "raw": items}
        except Exception as e:
            self.logger.error(f"Reddit fetch error: {e}")
            return {"topics": [], "raw": [], "error": str(e)}

    async def _fetch_news_trends(self, limit: int) -> Dict[str, Any]:
        """Fetch trends from NewsAPI."""
        try:
            # The method name in NewsAPIFetcher is fetch_health_headlines
            items = await self.newsapi_fetcher.fetch_health_headlines()
            topics = [item.get("title", "") for item in items[:limit] if item.get("title")]
            return {"topics": topics, "raw": items}
        except Exception as e:
            self.logger.error(f"NewsAPI fetch error: {e}")
            return {"topics": [], "raw": [], "error": str(e)}

    def build_context_block(self, trends: TrendContext) -> str:
        """
        Build a context block string for injection into agent prompts.

        Args:
            trends: TrendContext object

        Returns:
            Formatted string for prompt injection
        """
        return trends.to_context_block()
