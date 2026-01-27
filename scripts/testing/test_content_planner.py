#!/usr/bin/env python3
"""
Test script for content planner workflow.
Tests data fetching and planning logic with mock/real data.
"""
import asyncio
import logging
import yaml
from pathlib import Path

from agents.planners.content import ContentPlanner
from tools.fetchers import GoogleTrendsFetcher
from tools.fetchers import YouTubeTrendsFetcher
from tools.fetchers import NewsAPIFetcher
from tools.fetchers import RedditFetcher
from utils.pipeline.output_formatter import ContentOutputFormatter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_data_fetching(config: dict):
    """Test fetching data from all sources."""
    logger.info("=" * 60)
    logger.info("TEST 1: Data Fetching")
    logger.info("=" * 60)
    
    data_sources = config.get('data_sources', {})
    rate_limiting = config.get('rate_limiting', {})
    
    results = {}
    
    # Test Google Trends
    if data_sources.get('google_trends', {}).get('enabled', True):
        logger.info("\n📊 Testing Google Trends...")
        try:
            trends_limiter = None
            if rate_limiting.get('google_trends'):
                from utils.core.rate_limiter import RateLimiter
                rl_config = rate_limiting['google_trends']
                trends_limiter = RateLimiter(
                    max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                    max_requests_per_day=rl_config.get('max_requests_per_day')
                )
            fetcher = GoogleTrendsFetcher(rate_limiter=trends_limiter)
            trends = await fetcher.fetch_trends()
            results['google_trends'] = trends
            logger.info(f"✅ Google Trends: {len(trends)} items")
            if trends:
                logger.info(f"   Sample: {trends[0].get('title', 'N/A')[:60]}...")
        except Exception as e:
            logger.error(f"❌ Google Trends failed: {e}")
            results['google_trends'] = []
    
    # Test YouTube
    if data_sources.get('youtube', {}).get('enabled', True):
        logger.info("\n📺 Testing YouTube...")
        youtube_config = data_sources.get('youtube', {})
        api_key = youtube_config.get('api_key', '')
        if not api_key or api_key == '<YOUR_YOUTUBE_API_KEY>':
            logger.warning("⚠️  YouTube API key not configured, skipping")
            results['youtube'] = []
        else:
            try:
                youtube_limiter = None
                if rate_limiting.get('youtube'):
                    from utils.core.rate_limiter import RateLimiter
                    rl_config = rate_limiting['youtube']
                    youtube_limiter = RateLimiter(
                        max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                        max_requests_per_day=rl_config.get('max_requests_per_day')
                    )
                fetcher = YouTubeTrendsFetcher(
                    api_key=api_key,
                    rate_limiter=youtube_limiter,
                    max_results=youtube_config.get('max_results', 25)
                )
                youtube = await fetcher.fetch_trending()
                results['youtube'] = youtube
                logger.info(f"✅ YouTube: {len(youtube)} items")
                if youtube:
                    logger.info(f"   Sample: {youtube[0].get('snippet', {}).get('title', 'N/A')[:60]}...")
            except Exception as e:
                logger.error(f"❌ YouTube failed: {e}")
                results['youtube'] = []
    
    # Test NewsAPI
    if data_sources.get('newsapi', {}).get('enabled', True):
        logger.info("\n📰 Testing NewsAPI...")
        newsapi_config = data_sources.get('newsapi', {})
        api_key = newsapi_config.get('api_key', '')
        if not api_key or api_key == '<YOUR_NEWSAPI_KEY>':
            logger.warning("⚠️  NewsAPI key not configured, skipping")
            results['newsapi'] = []
        else:
            try:
                newsapi_limiter = None
                if rate_limiting.get('newsapi'):
                    from utils.core.rate_limiter import RateLimiter
                    rl_config = rate_limiting['newsapi']
                    newsapi_limiter = RateLimiter(
                        max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                        max_requests_per_day=rl_config.get('max_requests_per_day')
                    )
                fetcher = NewsAPIFetcher(
                    api_key=api_key,
                    rate_limiter=newsapi_limiter,
                    page_size=newsapi_config.get('page_size', 50)
                )
                news = await fetcher.fetch_health_headlines()
                results['newsapi'] = news
                logger.info(f"✅ NewsAPI: {len(news)} items")
                if news:
                    logger.info(f"   Sample: {news[0].get('title', 'N/A')[:60]}...")
            except Exception as e:
                logger.error(f"❌ NewsAPI failed: {e}")
                results['newsapi'] = []
    
    # Test Reddit
    if data_sources.get('reddit', {}).get('enabled', True):
        logger.info("\n🔴 Testing Reddit...")
        try:
            reddit_config = data_sources.get('reddit', {})
            reddit_limiter = None
            if rate_limiting.get('reddit'):
                from utils.core.rate_limiter import RateLimiter
                rl_config = rate_limiting['reddit']
                reddit_limiter = RateLimiter(
                    max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                    max_requests_per_day=rl_config.get('max_requests_per_day')
                )
            fetcher = RedditFetcher(
                rate_limiter=reddit_limiter,
                subreddits=reddit_config.get('subreddits'),
                limit=reddit_config.get('limit', 25)
            )
            reddit = await fetcher.fetch_all_subreddits()
            results['reddit'] = reddit
            logger.info(f"✅ Reddit: {len(reddit)} items")
            if reddit:
                logger.info(f"   Sample: {reddit[0].get('title', 'N/A')[:60]}...")
        except Exception as e:
            logger.error(f"❌ Reddit failed: {e}")
            results['reddit'] = []
    
    return results


async def test_planning(google_trends, youtube_items, newsapi_items, reddit_items):
    """Test content planning logic."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Content Planning")
    logger.info("=" * 60)
    
    planner = ContentPlanner()
    
    logger.info("\n🧠 Testing planning logic...")
    result = planner.plan_weekly_content(
        google_trends=google_trends,
        youtube_items=youtube_items,
        newsapi_items=newsapi_items,
        reddit_items=reddit_items,
        top_n=10
    )
    
    logger.info(f"\n✅ Planning complete!")
    logger.info(f"   - Top Clusters: {len(result.get('topClusters', []))}")
    logger.info(f"   - Long-form Topics: {len(result.get('longForm', []))}")
    logger.info(f"   - Calendar Days: {len(result.get('calendar7Days', []))}")
    
    # Show sample
    if result.get('topClusters'):
        logger.info(f"\n📊 Top 3 Clusters:")
        for i, cluster in enumerate(result['topClusters'][:3], 1):
            logger.info(f"   {i}. {cluster.get('displayTitle', cluster.get('topic', 'N/A'))[:60]}")
            logger.info(f"      Score: {cluster.get('score', 0):.1f} | Sources: {', '.join(cluster.get('sources', []))}")
    
    if result.get('longForm'):
        logger.info(f"\n📝 Long-form Topics:")
        for i, long_topic in enumerate(result['longForm'], 1):
            logger.info(f"   {i}. {long_topic.get('title', 'N/A')[:60]}")
    
    if result.get('calendar7Days'):
        logger.info(f"\n📅 Calendar (first 2 days):")
        for day_data in result['calendar7Days'][:2]:
            logger.info(f"   {day_data.get('day', 'N/A')}:")
            for j, short in enumerate(day_data.get('shorts', []), 1):
                logger.info(f"      Short {j}: {short.get('hook', 'N/A')[:50]}...")
    
    return result


async def test_output_formats(result):
    """Test output formatting."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Output Formatting")
    logger.info("=" * 60)
    
    formatter = ContentOutputFormatter()
    
    # Test JSON
    logger.info("\n📄 Testing JSON output...")
    json_str = formatter.to_json(result)
    logger.info(f"✅ JSON: {len(json_str)} characters")
    
    # Test Markdown
    logger.info("\n📝 Testing Markdown output...")
    md_str = formatter.to_markdown(result)
    logger.info(f"✅ Markdown: {len(md_str)} characters")
    
    # Test Email
    logger.info("\n📧 Testing Email output...")
    email_str = formatter.to_email_text(result)
    logger.info(f"✅ Email: {len(email_str)} characters")
    
    # Test Google Sheets rows
    logger.info("\n📊 Testing Google Sheets format...")
    rows = formatter.to_google_sheets_rows(result)
    logger.info(f"✅ Google Sheets: {len(rows)} rows")
    
    # Test Slack
    logger.info("\n💬 Testing Slack format...")
    slack_msg = formatter.to_slack_message(result)
    logger.info(f"✅ Slack: {len(slack_msg.get('blocks', []))} blocks")
    
    return {
        'json': json_str,
        'markdown': md_str,
        'email': email_str,
        'sheets_rows': rows,
        'slack': slack_msg
    }


async def main():
    """Main test function."""
    config_path = Path(__file__).parent / 'configs' / 'content_planner.yaml'
    
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        logger.info("Creating sample config...")
        # Create a minimal config for testing
        sample_config = {
            'data_sources': {
                'google_trends': {'enabled': True},
                'youtube': {'enabled': False, 'api_key': '<YOUR_YOUTUBE_API_KEY>'},
                'newsapi': {'enabled': False, 'api_key': '<YOUR_NEWSAPI_KEY>'},
                'reddit': {'enabled': True, 'subreddits': ['nutrition', 'Fitness'], 'limit': 10}
            },
            'planner': {'top_n_clusters': 10},
            'rate_limiting': {},
            'output': {'working_dir': '.working_dir/content_planner', 'formats': {'json': True, 'markdown': True}}
        }
        with open(config_path, 'w') as f:
            yaml.dump(sample_config, f, default_flow_style=False)
        logger.info(f"Created sample config at {config_path}")
        logger.info("Please update with your API keys for full testing")
        config = sample_config
    else:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    
    logger.info("🧪 Starting Content Planner Tests")
    logger.info("=" * 60)
    
    # Test 1: Data Fetching
    results = await test_data_fetching(config)
    
    # Test 2: Planning (only if we have some data)
    total_items = sum(len(v) for v in results.values())
    if total_items > 0:
        result = await test_planning(
            results.get('google_trends', []),
            results.get('youtube', []),
            results.get('newsapi', []),
            results.get('reddit', [])
        )
        
        # Test 3: Output Formats
        outputs = await test_output_formats(result)
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ All tests completed successfully!")
        logger.info("=" * 60)
    else:
        logger.warning("\n⚠️  No data fetched. Please configure API keys in configs/pipelines/content_planner.yaml")
        logger.info("   At minimum, Google Trends and Reddit work without API keys")


if __name__ == "__main__":
    asyncio.run(main())
