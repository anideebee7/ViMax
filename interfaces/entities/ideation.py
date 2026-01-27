"""Ideation interfaces for auto-generated content ideas."""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class IdeationResult(BaseModel):
    """Result of auto-ideation process."""
    
    idea: str = Field(
        description="The generated idea/concept for content creation"
    )
    title: str = Field(
        description="A catchy title for the content"
    )
    hook: Optional[str] = Field(
        default=None,
        description="An attention-grabbing hook or opening line"
    )
    target_audience: str = Field(
        description="The intended audience for this content"
    )
    content_type: str = Field(
        description="Type of content (video, song, documentary, ad, etc.)"
    )
    tone: str = Field(
        description="The tone/mood of the content (humorous, educational, inspiring, etc.)"
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="SEO/discovery keywords for the content"
    )
    hashtags: List[str] = Field(
        default_factory=list,
        description="Suggested hashtags for social media"
    )
    trend_alignment: Optional[str] = Field(
        default=None,
        description="How this idea aligns with current trends"
    )
    virality_factors: List[str] = Field(
        default_factory=list,
        description="Elements that could make this content viral"
    )
    estimated_duration: Optional[str] = Field(
        default=None,
        description="Suggested duration for the content"
    )
    ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = Field(
        description="The mode used to generate this idea"
    )
    confidence_score: float = Field(
        default=0.7,
        description="Confidence score for this idea (0-1)"
    )
    
    def to_prompt(self) -> str:
        """Convert ideation result to a prompt string for pipelines."""
        parts = [f"Title: {self.title}", f"Idea: {self.idea}"]
        if self.hook:
            parts.append(f"Hook: {self.hook}")
        parts.append(f"Target Audience: {self.target_audience}")
        parts.append(f"Tone: {self.tone}")
        if self.keywords:
            parts.append(f"Keywords: {', '.join(self.keywords)}")
        if self.trend_alignment:
            parts.append(f"Trend Alignment: {self.trend_alignment}")
        if self.virality_factors:
            parts.append(f"Virality Factors: {', '.join(self.virality_factors)}")
        if self.estimated_duration:
            parts.append(f"Duration: {self.estimated_duration}")
        return "\n".join(parts)


class PodcastEpisodeIdea(BaseModel):
    """Idea for a podcast episode that can be turned into video content."""
    
    episode_title: str = Field(
        description="Title of the podcast episode"
    )
    topic: str = Field(
        description="Main topic to discuss"
    )
    key_points: List[str] = Field(
        description="Key discussion points"
    )
    guest_suggestion: Optional[str] = Field(
        default=None,
        description="Suggested guest or expert to feature"
    )
    call_to_action: Optional[str] = Field(
        default=None,
        description="Call to action for listeners"
    )
    visual_opportunities: List[str] = Field(
        default_factory=list,
        description="Opportunities for visual content in video adaptation"
    )


class SeriesIdeation(BaseModel):
    """Ideas for a content series (multiple episodes)."""
    
    series_name: str = Field(
        description="Name of the content series"
    )
    series_concept: str = Field(
        description="Overall concept and theme of the series"
    )
    episode_ideas: List[IdeationResult] = Field(
        description="Individual episode ideas"
    )
    recurring_elements: List[str] = Field(
        default_factory=list,
        description="Elements that recur across episodes"
    )
    target_episode_count: int = Field(
        default=5,
        description="Target number of episodes"
    )
