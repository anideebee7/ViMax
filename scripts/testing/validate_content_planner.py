#!/usr/bin/env python3
"""
Comprehensive validation script for the Content Planner workflow.
Tests all components: data fetching, planning logic, and output formatting.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List

import yaml

from agents.planners.content import ContentPlanner
from tools.fetchers import GoogleTrendsFetcher
from tools.fetchers import NewsAPIFetcher
from tools.fetchers import RedditFetcher
from tools.fetchers import YouTubeTrendsFetcher
from utils.pipeline.output_formatter import ContentOutputFormatter
from utils.core.rate_limiter import RateLimiter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def validate_data_fetching(config: Dict) -> Dict[str, List]:
    """Validate data fetching from all enabled sources."""
    logger.info("=" * 60)
    logger.info("VALIDATION 1: Data Fetching")
    logger.info("=" * 60)
    
    results = {
        'google_trends': [],
        'youtube': [],
        'newsapi': [],
        'reddit': []
    }
    
    rate_limiting = config.get('rate_limiting', {})
    
    # Google Trends
    if config.get('data_sources', {}).get('google_trends', {}).get('enabled', True):
        try:
            trends_limiter = None
            if rate_limiting.get('google_trends'):
                rl_config = rate_limiting['google_trends']
                trends_limiter = RateLimiter(
                    max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                    max_requests_per_day=rl_config.get('max_requests_per_day')
                )
            fetcher = GoogleTrendsFetcher(rate_limiter=trends_limiter)
            items = await fetcher.fetch_trends()
            results['google_trends'] = items
            logger.info(f"✅ Google Trends: {len(items)} items fetched")
        except Exception as e:
            logger.error(f"❌ Google Trends failed: {e}")
    
    # YouTube
    youtube_config = config.get('data_sources', {}).get('youtube', {})
    if youtube_config.get('enabled', False) and youtube_config.get('api_key') and youtube_config.get('api_key') != '<YOUR_YOUTUBE_API_KEY>':
        try:
            youtube_limiter = None
            if rate_limiting.get('youtube'):
                rl_config = rate_limiting['youtube']
                youtube_limiter = RateLimiter(
                    max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                    max_requests_per_day=rl_config.get('max_requests_per_day')
                )
            fetcher = YouTubeTrendsFetcher(
                api_key=youtube_config['api_key'],
                rate_limiter=youtube_limiter,
                max_results=youtube_config.get('max_results', 25)
            )
            items = await fetcher.fetch_trending()
            results['youtube'] = items
            logger.info(f"✅ YouTube: {len(items)} items fetched")
        except Exception as e:
            logger.error(f"❌ YouTube failed: {e}")
    else:
        logger.warning("⚠️  YouTube disabled or API key missing")
    
    # NewsAPI
    newsapi_config = config.get('data_sources', {}).get('newsapi', {})
    if newsapi_config.get('enabled', False) and newsapi_config.get('api_key') and newsapi_config.get('api_key') != '<YOUR_NEWSAPI_KEY>':
        try:
            newsapi_limiter = None
            if rate_limiting.get('newsapi'):
                rl_config = rate_limiting['newsapi']
                newsapi_limiter = RateLimiter(
                    max_requests_per_minute=rl_config.get('max_requests_per_minute'),
                    max_requests_per_day=rl_config.get('max_requests_per_day')
                )
            fetcher = NewsAPIFetcher(
                api_key=newsapi_config['api_key'],
                rate_limiter=newsapi_limiter,
                page_size=newsapi_config.get('page_size', 50)
            )
            items = await fetcher.fetch_health_headlines()
            results['newsapi'] = items
            logger.info(f"✅ NewsAPI: {len(items)} items fetched")
        except Exception as e:
            logger.error(f"❌ NewsAPI failed: {e}")
    else:
        logger.warning("⚠️  NewsAPI disabled or API key missing")
    
    # Reddit
    reddit_config = config.get('data_sources', {}).get('reddit', {})
    if reddit_config.get('enabled', True):
        try:
            reddit_limiter = None
            if rate_limiting.get('reddit'):
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
            items = await fetcher.fetch_all_subreddits()
            results['reddit'] = items
            logger.info(f"✅ Reddit: {len(items)} items fetched")
        except Exception as e:
            logger.error(f"❌ Reddit failed: {e}")
    
    total_items = sum(len(v) for v in results.values())
    logger.info(f"\n📊 Total items fetched: {total_items}")
    
    if total_items == 0:
        logger.error("❌ CRITICAL: No data fetched from any source!")
        return results
    
    logger.info("✅ Data fetching validation passed\n")
    return results


def validate_planning_logic(data: Dict[str, List]) -> Dict:
    """Validate content planning logic."""
    logger.info("=" * 60)
    logger.info("VALIDATION 2: Content Planning Logic")
    logger.info("=" * 60)
    
    planner = ContentPlanner()
    
    try:
        result = planner.plan_weekly_content(
            google_trends=data.get('google_trends', []),
            youtube_items=data.get('youtube', []),
            newsapi_items=data.get('newsapi', []),
            reddit_items=data.get('reddit', []),
            top_n=10
        )
        
        # Validate structure
        assert 'topClusters' in result, "Missing 'topClusters' in result"
        assert 'longForm' in result, "Missing 'longForm' in result"
        assert 'calendar7Days' in result, "Missing 'calendar7Days' in result"
        
        # Validate top clusters
        clusters = result['topClusters']
        assert len(clusters) > 0, "No clusters generated"
        assert len(clusters) <= 10, f"Too many clusters: {len(clusters)}"
        
        for cluster in clusters:
            assert 'topic' in cluster, "Cluster missing 'topic'"
            assert 'score' in cluster, "Cluster missing 'score'"
            assert 'pillar' in cluster, "Cluster missing 'pillar'"
            assert 'sources' in cluster, "Cluster missing 'sources'"
            assert isinstance(cluster['score'], (int, float)), "Score must be numeric"
            assert cluster['score'] >= 0, "Score must be non-negative"
        
        # Validate long-form topics
        long_form = result['longForm']
        assert len(long_form) <= 2, f"Too many long-form topics: {len(long_form)}"
        
        for lf in long_form:
            assert 'title' in lf, "Long-form missing 'title'"
            assert 'topic' in lf, "Long-form missing 'topic'"
        
        # Validate calendar
        calendar = result['calendar7Days']
        assert len(calendar) == 7, f"Calendar must have 7 days, got {len(calendar)}"
        
        for day in calendar:
            assert 'day' in day, "Day missing 'day' field"
            assert 'shorts' in day, "Day missing 'shorts' field"
            assert len(day['shorts']) == 2, f"Day must have 2 shorts, got {len(day['shorts'])}"
            
            for short in day['shorts']:
                assert 'hook' in short, "Short missing 'hook'"
                assert 'topic' in short, "Short missing 'topic'"
                assert 'pillar' in short, "Short missing 'pillar'"
        
        logger.info(f"✅ Generated {len(clusters)} top clusters")
        logger.info(f"✅ Generated {len(long_form)} long-form topics")
        logger.info(f"✅ Generated 7-day calendar with {sum(len(d['shorts']) for d in calendar)} shorts")
        logger.info("✅ Content planning logic validation passed\n")
        
        return result
        
    except AssertionError as e:
        logger.error(f"❌ Planning validation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Planning error: {e}")
        raise


def validate_output_formats(result: Dict) -> Dict[str, str]:
    """Validate all output formatters."""
    logger.info("=" * 60)
    logger.info("VALIDATION 3: Output Formatting")
    logger.info("=" * 60)
    
    outputs = {}
    
    try:
        # JSON
        json_output = ContentOutputFormatter.to_json(result)
        assert json_output, "JSON output is empty"
        # Validate it's valid JSON
        json.loads(json_output)
        outputs['json'] = json_output
        logger.info("✅ JSON formatter works")
        
        # Markdown
        md_output = ContentOutputFormatter.to_markdown(result)
        assert md_output, "Markdown output is empty"
        assert '# Weekly Content Plan' in md_output, "Markdown missing header"
        outputs['markdown'] = md_output
        logger.info("✅ Markdown formatter works")
        
        # Email
        email_output = ContentOutputFormatter.to_email_text(result)
        assert email_output, "Email output is empty"
        outputs['email'] = email_output
        logger.info("✅ Email formatter works")
        
        # Google Sheets
        sheets_rows = ContentOutputFormatter.to_google_sheets_rows(result)
        assert sheets_rows, "Google Sheets output is empty"
        assert len(sheets_rows) >= 7, "Google Sheets must have at least 7 rows (one per day)"
        outputs['google_sheets'] = sheets_rows
        logger.info(f"✅ Google Sheets formatter works ({len(sheets_rows)} rows)")
        
        # Slack
        slack_blocks = ContentOutputFormatter.to_slack_message(result)
        assert slack_blocks, "Slack output is empty"
        assert isinstance(slack_blocks, dict), "Slack output must be a dict"
        assert 'blocks' in slack_blocks, "Slack output must have 'blocks' key"
        outputs['slack'] = slack_blocks
        logger.info("✅ Slack formatter works")
        
        logger.info("✅ All output formatters validation passed\n")
        return outputs
        
    except AssertionError as e:
        logger.error(f"❌ Output formatting validation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Output formatting error: {e}")
        raise


def validate_file_generation(outputs: Dict[str, str], result: Dict) -> None:
    """Validate that output files are generated correctly."""
    logger.info("=" * 60)
    logger.info("VALIDATION 4: File Generation")
    logger.info("=" * 60)
    
    from datetime import datetime
    from utils.pipeline.output_formatter import ContentOutputFormatter
    
    output_dir = Path(__file__).parent / '.working_dir' / 'content_planner'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y-%m-%d')
    
    # Generate files
    json_path = output_dir / f'weekly_plan_{timestamp}.json'
    md_path = output_dir / f'weekly_plan_{timestamp}.md'
    email_path = output_dir / f'weekly_plan_{timestamp}_email.txt'
    
    json_path.write_text(outputs['json'])
    md_path.write_text(outputs['markdown'])
    email_path.write_text(outputs['email'])
    
    # Validate files exist and are non-empty
    assert json_path.exists(), f"JSON file not created: {json_path}"
    assert json_path.stat().st_size > 0, "JSON file is empty"
    logger.info(f"✅ JSON file created: {json_path}")
    
    assert md_path.exists(), f"Markdown file not created: {md_path}"
    assert md_path.stat().st_size > 0, "Markdown file is empty"
    logger.info(f"✅ Markdown file created: {md_path}")
    
    assert email_path.exists(), f"Email file not created: {email_path}"
    assert email_path.stat().st_size > 0, "Email file is empty"
    logger.info(f"✅ Email file created: {email_path}")
    
    logger.info("✅ File generation validation passed\n")


async def main():
    """Run all validation tests."""
    logger.info("\n" + "=" * 60)
    logger.info("CONTENT PLANNER VALIDATION SUITE")
    logger.info("=" * 60 + "\n")
    
    config_path = Path(__file__).parent / 'configs' / 'content_planner.yaml'
    
    if not config_path.exists():
        logger.error(f"❌ Config file not found: {config_path}")
        logger.info("Please create configs/pipelines/content_planner.yaml first")
        return
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    try:
        # Validation 1: Data Fetching
        data = await validate_data_fetching(config)
        
        if sum(len(v) for v in data.values()) == 0:
            logger.error("\n❌ VALIDATION FAILED: No data fetched")
            logger.info("Please configure API keys in configs/pipelines/content_planner.yaml")
            return
        
        # Validation 2: Planning Logic
        result = validate_planning_logic(data)
        
        # Validation 3: Output Formatting
        outputs = validate_output_formats(result)
        
        # Validation 4: File Generation
        validate_file_generation(outputs, result)
        
        # Summary
        logger.info("=" * 60)
        logger.info("✅ ALL VALIDATIONS PASSED!")
        logger.info("=" * 60)
        logger.info(f"\n📊 Summary:")
        logger.info(f"   - Data sources: {sum(1 for v in data.values() if len(v) > 0)}/{len(data)}")
        logger.info(f"   - Total items: {sum(len(v) for v in data.values())}")
        logger.info(f"   - Top clusters: {len(result['topClusters'])}")
        logger.info(f"   - Long-form: {len(result['longForm'])}")
        logger.info(f"   - Calendar days: {len(result['calendar7Days'])}")
        logger.info(f"   - Output formats: {len(outputs)}")
        logger.info("\n🎉 Content Planner workflow is fully validated!\n")
        
    except Exception as e:
        logger.error(f"\n❌ VALIDATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    exit(exit_code)
