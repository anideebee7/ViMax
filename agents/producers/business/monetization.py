"""Monetization advisor agent for generating platform and marketing recommendations."""

from typing import Optional, List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from interfaces.output.monetization import MonetizationPlan, PlatformRecommendation
from utils.core.retry import after_func


SYSTEM_PROMPT = """
[Role]
You are an expert digital marketing strategist and content monetization advisor.
You specialize in maximizing reach, engagement, and revenue for digital content across platforms.

[Task]
Analyze the provided content metadata and target audience to generate a comprehensive
monetization and distribution strategy.

[Output]
{format_instructions}

[Platform Expertise]
- YouTube: Long-form (8-20min), Shorts (15-60s), monetization via Partner Program, sponsorships
- TikTok: Short-form (15-60s), viral hooks, trending sounds, Creator Fund
- Instagram: Reels (15-90s), Stories, Posts, shopping integration
- Pinterest: Pins, video pins, affiliate marketing, shopping
- Spotify: Music, podcasts, playlists
- SoundCloud: Music distribution, fan engagement
- Twitch: Live streaming, subscriptions, donations
- LinkedIn: Professional content, B2B marketing
- Twitter/X: Short updates, threads, engagement

[Monetization Strategies]
- Ad revenue (platform partner programs)
- Sponsorships and brand deals
- Affiliate marketing
- Merchandise sales
- Digital products (courses, ebooks)
- Memberships and subscriptions
- Licensing and syndication
- Crowdfunding

[Virality Factors]
- Hook in first 3 seconds
- Emotional resonance
- Trending topics/sounds
- Clear call-to-action
- Shareability
- Controversy (appropriate)
- Educational value
- Entertainment value
"""

HUMAN_PROMPT = """
<CONTENT_TYPE>
{content_type}
</CONTENT_TYPE>

<CONTENT_SUMMARY>
{content_summary}
</CONTENT_SUMMARY>

<TARGET_AUDIENCE>
{audience}
</TARGET_AUDIENCE>

<CONTENT_DURATION>
{duration}
</CONTENT_DURATION>

<GENRE_OR_CATEGORY>
{genre}
</GENRE_OR_CATEGORY>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Based on this content, provide a comprehensive monetization and distribution strategy.
Consider the target audience, content type, and current platform trends.
"""


class MonetizationAdvisor:
    """Agent that provides monetization and platform distribution recommendations."""

    def __init__(self, chat_model):
        """
        Initialize MonetizationAdvisor.

        Args:
            chat_model: LangChain chat model instance
        """
        self.chat_model = chat_model

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def advise(
        self,
        content_type: str,
        content_summary: str,
        audience: str,
        duration: Optional[str] = None,
        genre: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> MonetizationPlan:
        """
        Generate monetization recommendations for content.

        Args:
            content_type: Type of content (video, song, podcast, ad, etc.)
            content_summary: Brief summary of the content
            audience: Target audience description
            duration: Content duration (e.g., "60s", "10 minutes")
            genre: Genre or category
            additional_context: Any additional context (trends, keywords, etc.)

        Returns:
            MonetizationPlan with platform recommendations and strategy
        """
        parser = PydanticOutputParser(pydantic_object=MonetizationPlan)

        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT.format(
                    format_instructions=parser.get_format_instructions()
                )
            ),
            HumanMessage(
                content=HUMAN_PROMPT.format(
                    content_type=content_type,
                    content_summary=content_summary,
                    audience=audience,
                    duration=duration or "Not specified",
                    genre=genre or "General",
                    additional_context=additional_context or "None",
                )
            ),
        ]

        chain = self.chat_model | parser
        return await chain.ainvoke(messages)

    async def advise_for_video(
        self,
        title: str,
        description: str,
        audience: str,
        duration_seconds: int,
        genre: Optional[str] = None,
        is_shorts: bool = False,
        trend_context: Optional[str] = None,
    ) -> MonetizationPlan:
        """Convenience method for video content."""
        content_type = "YouTube Shorts / TikTok / Reels" if is_shorts else "Video"
        duration = f"{duration_seconds}s" if duration_seconds < 120 else f"{duration_seconds // 60} minutes"

        return await self.advise(
            content_type=content_type,
            content_summary=f"Title: {title}\n\nDescription: {description}",
            audience=audience,
            duration=duration,
            genre=genre,
            additional_context=trend_context,
        )

    async def advise_for_music(
        self,
        title: str,
        genre: str,
        mood: str,
        audience: str,
        duration_seconds: int,
        lyrics_preview: Optional[str] = None,
        trend_context: Optional[str] = None,
    ) -> MonetizationPlan:
        """Convenience method for music content."""
        summary = f"Title: {title}\nGenre: {genre}\nMood: {mood}"
        if lyrics_preview:
            summary += f"\n\nLyrics Preview:\n{lyrics_preview[:200]}..."

        return await self.advise(
            content_type="Music / Song",
            content_summary=summary,
            audience=audience,
            duration=f"{duration_seconds}s",
            genre=genre,
            additional_context=trend_context,
        )

    async def advise_for_podcast(
        self,
        title: str,
        description: str,
        audience: str,
        duration_minutes: int,
        category: Optional[str] = None,
        trend_context: Optional[str] = None,
    ) -> MonetizationPlan:
        """Convenience method for podcast content."""
        return await self.advise(
            content_type="Podcast Episode",
            content_summary=f"Title: {title}\n\nDescription: {description}",
            audience=audience,
            duration=f"{duration_minutes} minutes",
            genre=category,
            additional_context=trend_context,
        )

    async def advise_for_ad(
        self,
        brand: str,
        product: str,
        campaign_goal: str,
        audience: str,
        ad_format: str,
        trend_context: Optional[str] = None,
    ) -> MonetizationPlan:
        """Convenience method for advertisement content."""
        summary = f"Brand: {brand}\nProduct: {product}\nCampaign Goal: {campaign_goal}"

        return await self.advise(
            content_type=f"Advertisement ({ad_format})",
            content_summary=summary,
            audience=audience,
            duration=ad_format,
            genre="Advertising",
            additional_context=trend_context,
        )

    async def advise_for_educational(
        self,
        topic: str,
        description: str,
        audience: str,
        duration_minutes: int,
        is_series: bool = False,
        num_episodes: int = 1,
        trend_context: Optional[str] = None,
    ) -> MonetizationPlan:
        """Convenience method for educational content."""
        content_type = "Educational Series" if is_series else "Educational Video"
        summary = f"Topic: {topic}\n\nDescription: {description}"
        if is_series:
            summary += f"\n\nSeries: {num_episodes} episodes"

        return await self.advise(
            content_type=content_type,
            content_summary=summary,
            audience=audience,
            duration=f"{duration_minutes} minutes per episode" if is_series else f"{duration_minutes} minutes",
            genre="Education",
            additional_context=trend_context,
        )
