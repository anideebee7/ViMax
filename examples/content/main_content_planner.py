#!/usr/bin/env python3
"""
Main script for weekly health content planning workflow.

This script:
1. Fetches trending topics from Google Trends, YouTube, NewsAPI, and Reddit
2. Filters to health niche only
3. Clusters and scores topics
4. Generates weekly calendar (2 Shorts/day + 2 Long-form topics)
5. Outputs results in multiple formats (JSON, Markdown, Email, etc.)
"""
import asyncio
import logging
import yaml
from pathlib import Path
from typing import Dict, List

from agents.planners.content import ContentPlanner
from tools.fetchers import GoogleTrendsFetcher
from tools.fetchers import YouTubeTrendsFetcher
from tools.fetchers import NewsAPIFetcher
from tools.fetchers import RedditFetcher
from utils.pipeline.output_formatter import ContentOutputFormatter
from utils.core.rate_limiter import RateLimiter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def fetch_all_sources(config: Dict) -> tuple:
    """
    Fetch data from all configured sources in parallel.

    Args:
        config: Configuration dictionary

    Returns:
        Tuple of (google_trends, youtube_items, newsapi_items, reddit_items)
    """
    data_sources = config.get('data_sources', {})
    rate_limiting = config.get('rate_limiting', {})
    
    tasks = []
    
    # Google Trends
    if data_sources.get('google_trends', {}).get('enabled', True):
        trends_limiter = None
        if rate_limiting.get('google_trends'):
            rl_config = rate_limiting['google_trends']
            trends_limiter = RateLimiter(
                max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                max_requests_per_day=rl_config.get('max_requests_per_day')
            )
        trends_fetcher = GoogleTrendsFetcher(rate_limiter=trends_limiter)
        tasks.append(('google_trends', trends_fetcher.fetch_trends()))
    else:
        tasks.append(('google_trends', asyncio.create_task(asyncio.sleep(0, result=[]))))
    
    # YouTube
    if data_sources.get('youtube', {}).get('enabled', True):
        youtube_config = data_sources.get('youtube', {})
        api_key = youtube_config.get('api_key', '')
        if not api_key or api_key == '<YOUR_YOUTUBE_API_KEY>':
            logger.warning("YouTube API key not configured, skipping YouTube trends")
            tasks.append(('youtube', asyncio.create_task(asyncio.sleep(0, result=[]))))
        else:
            youtube_limiter = None
            if rate_limiting.get('youtube'):
                rl_config = rate_limiting['youtube']
                youtube_limiter = RateLimiter(
                    max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                    max_requests_per_day=rl_config.get('max_requests_per_day')
                )
            youtube_fetcher = YouTubeTrendsFetcher(
                api_key=api_key,
                rate_limiter=youtube_limiter,
                max_results=youtube_config.get('max_results', 25)
            )
            tasks.append(('youtube', youtube_fetcher.fetch_trending()))
    else:
        tasks.append(('youtube', asyncio.create_task(asyncio.sleep(0, result=[]))))
    
    # NewsAPI
    if data_sources.get('newsapi', {}).get('enabled', True):
        newsapi_config = data_sources.get('newsapi', {})
        api_key = newsapi_config.get('api_key', '')
        if not api_key or api_key == '<YOUR_NEWSAPI_KEY>':
            logger.warning("NewsAPI key not configured, skipping NewsAPI headlines")
            tasks.append(('newsapi', asyncio.create_task(asyncio.sleep(0, result=[]))))
        else:
            newsapi_limiter = None
            if rate_limiting.get('newsapi'):
                rl_config = rate_limiting['newsapi']
                newsapi_limiter = RateLimiter(
                    max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                    max_requests_per_day=rl_config.get('max_requests_per_day')
                )
            newsapi_fetcher = NewsAPIFetcher(
                api_key=api_key,
                rate_limiter=newsapi_limiter,
                page_size=newsapi_config.get('page_size', 50)
            )
            tasks.append(('newsapi', newsapi_fetcher.fetch_health_headlines()))
    else:
        tasks.append(('newsapi', asyncio.create_task(asyncio.sleep(0, result=[]))))
    
    # Reddit
    if data_sources.get('reddit', {}).get('enabled', True):
        reddit_config = data_sources.get('reddit', {})
        reddit_limiter = None
        if rate_limiting.get('reddit'):
            rl_config = rate_limiting['reddit']
            reddit_limiter = RateLimiter(
                max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                max_requests_per_day=rl_config.get('max_requests_per_day')
            )
        reddit_fetcher = RedditFetcher(
            rate_limiter=reddit_limiter,
            subreddits=reddit_config.get('subreddits'),
            limit=reddit_config.get('limit', 25)
        )
        tasks.append(('reddit', reddit_fetcher.fetch_all_subreddits()))
    else:
        tasks.append(('reddit', asyncio.create_task(asyncio.sleep(0, result=[]))))
    
    # Execute all fetches in parallel
    results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
    
    # Map results back to source names
    result_dict = {}
    for (source_name, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.error(f"Error fetching {source_name}: {result}")
            result_dict[source_name] = []
        else:
            result_dict[source_name] = result
    
    return (
        result_dict.get('google_trends', []),
        result_dict.get('youtube', []),
        result_dict.get('newsapi', []),
        result_dict.get('reddit', [])
    )


async def main():
    """Main execution function."""
    # Load configuration
    config_path = Path(__file__).parent / 'configs' / 'content_planner.yaml'
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        logger.info("Please create configs/pipelines/content_planner.yaml with your API keys")
        return
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    logger.info("🚀 Starting weekly content planning workflow...")
    logger.info("=" * 60)
    
    # Fetch data from all sources
    logger.info("📊 Fetching data from all sources...")
    google_trends, youtube_items, newsapi_items, reddit_items = await fetch_all_sources(config)
    
    logger.info(f"✅ Fetched:")
    logger.info(f"   - Google Trends: {len(google_trends)} items")
    logger.info(f"   - YouTube: {len(youtube_items)} items")
    logger.info(f"   - NewsAPI: {len(newsapi_items)} items")
    logger.info(f"   - Reddit: {len(reddit_items)} items")
    logger.info("")
    
    # Plan content
    logger.info("🧠 Planning weekly content...")
    planner = ContentPlanner()
    planner_config = config.get('planner', {})
    
    result = planner.plan_weekly_content(
        google_trends=google_trends,
        youtube_items=youtube_items,
        newsapi_items=newsapi_items,
        reddit_items=reddit_items,
        top_n=planner_config.get('top_n_clusters', 10)
    )
    
    logger.info("✅ Content planning complete!")
    logger.info("")
    
    # Output results
    logger.info("📤 Generating outputs...")
    output_config = config.get('output', {})
    working_dir = Path(output_config.get('working_dir', '.working_dir/content_planner'))
    working_dir.mkdir(parents=True, exist_ok=True)
    
    formats = output_config.get('formats', {})
    formatter = ContentOutputFormatter()
    
    # JSON output
    if formats.get('json', True):
        json_path = working_dir / f"weekly_plan_{result['generatedAt'][:10]}.json"
        formatter.to_json(result, str(json_path))
        logger.info(f"   ✅ JSON: {json_path}")
    
    # Markdown output
    if formats.get('markdown', True):
        md_path = working_dir / f"weekly_plan_{result['generatedAt'][:10]}.md"
        md_content = formatter.to_markdown(result)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        logger.info(f"   ✅ Markdown: {md_path}")
    
    # Email output
    if formats.get('email', False):
        email_config = output_config.get('email', {})
        email_text = formatter.to_email_text(result)
        email_path = working_dir / f"weekly_plan_{result['generatedAt'][:10]}_email.txt"
        with open(email_path, 'w', encoding='utf-8') as f:
            f.write(email_text)
        logger.info(f"   ✅ Email text: {email_path}")
        # TODO: Actually send email if email_config has 'to' address
    
    # Google Sheets output
    if formats.get('google_sheets', False):
        sheets_config = output_config.get('google_sheets', {})
        rows = formatter.to_google_sheets_rows(result)
        # TODO: Implement Google Sheets API integration
        logger.info(f"   ⚠️  Google Sheets: {len(rows)} rows ready (API integration pending)")
    
    # Slack output
    if formats.get('slack', False):
        slack_config = output_config.get('slack', {})
        slack_message = formatter.to_slack_message(result)
        # TODO: Actually post to Slack if webhook_url is configured
        logger.info(f"   ⚠️  Slack: Message ready (webhook integration pending)")
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ Weekly content planning complete!")
    logger.info("")
    logger.info("📋 Summary:")
    logger.info(f"   - Top Clusters: {len(result.get('topClusters', []))}")
    logger.info(f"   - Long-form Topics: {len(result.get('longForm', []))}")
    logger.info(f"   - Calendar Days: {len(result.get('calendar7Days', []))}")
    logger.info("")
    logger.info(f"📁 Output directory: {working_dir}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
