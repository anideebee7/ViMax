"""Monetization output models for all pipelines."""

from typing import List, Optional
from pydantic import BaseModel, Field


class PlatformRecommendation(BaseModel):
    """Recommendation for a specific platform."""

    platform: str = Field(
        ..., description="Platform name (YouTube, TikTok, Instagram, Pinterest, Spotify, etc.)"
    )
    content_format: str = Field(
        ..., description="Content format (Shorts, Reels, Stories, Long-form, Pins, etc.)"
    )
    optimal_length: str = Field(
        ..., description="Optimal content length (e.g., '15-60s', '3-10min')"
    )
    posting_time: str = Field(
        ..., description="Best posting time (e.g., 'Weekdays 6-9pm EST')"
    )
    hashtags: List[str] = Field(
        default_factory=list, description="Recommended hashtags for discovery"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score for this recommendation (0-1)"
    )


class MonetizationPlan(BaseModel):
    """Complete monetization plan for generated content."""

    target_audience: str = Field(
        ..., description="Target audience description"
    )
    primary_platform: PlatformRecommendation = Field(
        ..., description="Primary platform recommendation"
    )
    secondary_platforms: List[PlatformRecommendation] = Field(
        default_factory=list, description="Secondary platform recommendations"
    )
    marketing_strategy: str = Field(
        ..., description="Marketing strategy for virality and engagement"
    )
    monetization_paths: List[str] = Field(
        default_factory=list,
        description="Available monetization paths (Ads, sponsorships, affiliate, etc.)",
    )
    virality_score: float = Field(
        ..., ge=0.0, le=100.0, description="Predicted virality score (0-100)"
    )
    content_pillars: List[str] = Field(
        default_factory=list, description="Content pillars/categories"
    )
    seo_keywords: List[str] = Field(
        default_factory=list, description="SEO keywords for discoverability"
    )
    call_to_action: Optional[str] = Field(
        None, description="Recommended call-to-action"
    )


class TrendContext(BaseModel):
    """Trend data context for content generation."""

    trending_topics: List[str] = Field(
        default_factory=list, description="Current trending topics"
    )
    trending_hashtags: List[str] = Field(
        default_factory=list, description="Trending hashtags"
    )
    trending_sounds: List[str] = Field(
        default_factory=list, description="Trending audio/sounds (for TikTok/Reels)"
    )
    news_topics: List[str] = Field(
        default_factory=list, description="Current news topics"
    )
    source_breakdown: dict = Field(
        default_factory=dict,
        description="Breakdown of trends by source (google, youtube, reddit, news)",
    )
    fetched_at: Optional[str] = Field(
        None, description="ISO timestamp when trends were fetched"
    )

    def to_context_block(self) -> str:
        """Format trend data as a context block for agent prompts."""
        lines = ["<TRENDING_CONTEXT>"]

        if self.trending_topics:
            lines.append("Trending Topics:")
            for topic in self.trending_topics[:10]:
                lines.append(f"  - {topic}")

        if self.trending_hashtags:
            lines.append("\nTrending Hashtags:")
            lines.append(f"  {', '.join(self.trending_hashtags[:15])}")

        if self.trending_sounds:
            lines.append("\nTrending Sounds/Audio:")
            for sound in self.trending_sounds[:5]:
                lines.append(f"  - {sound}")

        if self.news_topics:
            lines.append("\nCurrent News Topics:")
            for topic in self.news_topics[:5]:
                lines.append(f"  - {topic}")

        lines.append("</TRENDING_CONTEXT>")
        return "\n".join(lines)
