"""
Ad Banner Ideator Agent

Creates high-converting display ad banner concepts for brands and games.
Optimized for 25%+ CTR with multiple variants: creative, trend-based, and
conversion-focused. Produces headline, CTA, visual concept, and rationale
for each concept.
"""

from typing import Optional, List, Literal
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from utils.core.retry import after_func


SYSTEM_PROMPT = """
[Role]
You are an expert performance creative director specializing in HIGH-CONVERTING
display and social ad banners. Your banners routinely achieve 25%+ CTR in
campaigns. You understand IAB/Google Display sizes, Facebook/Instagram specs,
and what makes users stop and click.

[Task]
Create multiple ad banner concepts for a brand or game. Each concept must be
designed to achieve 25%+ click-through rate through proven conversion principles.

[Output]
{format_instructions}

[CTR Principles - 25%+ Target]
- HOOK: First 0.5 seconds must grab attention (contrast, face, motion, question)
- CLARITY: One primary message; no more than 5 words in headline
- URGENCY: Scarcity, limited time, or FOMO when authentic
- SOCIAL PROOF: "Join 2M+", ratings, awards—when true
- CTA: Action verb + benefit; button-style copy (Play Free, Download, Shop Now)
- CONTRAST: High contrast between CTA and background; thumb-stopping color
- FACES: Human faces (especially eyes) increase CTR 20-40% when relevant
- NEGATIVE SPACE: 30-40% empty so eyes go to CTA
- MOBILE-FIRST: 60%+ traffic is mobile; legible at 320px width

[Variant Styles]
1. CREATIVE: Bold, unexpected, memorable; differentiation over literal
2. TREND: Tied to current trends, memes, or cultural moments when relevant
3. HIGH_CONVERTING: Best-practice formula: problem/solution + proof + urgent CTA
4. CHARACTER_PROMO: Hero shot of the brand/game character; character is the focus, interacting with the user or product

[Format]
- Every concept needs a VISUAL_PROMPT: a single, detailed sentence for AI image
  generation. Include: subject, mood, composition, colors, text placement, style.
- CTR_RATIONALE: 2-3 sentences on why this concept can hit 25%+ CTR.
"""

HUMAN_PROMPT = """
<ENTITY>
{brand_or_game}
{entity_context}
</ENTITY>

<BRIEF>
{brief}
</BRIEF>

<TARGET_AUDIENCE>
{audience}
</TARGET_AUDIENCE>

<CAMPAIGN_GOAL>
{campaign_goal}
</CAMPAIGN_GOAL>

<PLATFORMS>
{platforms}
</PLATFORMS>

<TREND_CONTEXT>
{trend_context}
</TREND_CONTEXT>

<ADDITIONAL>
{additional}
</ADDITIONAL>

Create {num_concepts} high-converting ad banner concepts. Include at least one
CREATIVE, one TREND-based (if trend context exists), and one HIGH_CONVERTING.
Each must have a clear VISUAL_PROMPT for image generation and a CTR_RATIONALE
for 25%+ performance. Recommend which standard ad sizes fit each concept best.
"""


class BannerConcept(BaseModel):
    """A single ad banner concept optimized for high CTR."""

    style: str = Field(
        ...,
        description="One of: creative, trend, high_converting",
    )
    headline: str = Field(..., description="Primary headline, max 5–7 words")
    subheadline: Optional[str] = Field(None, description="Optional supporting line")
    cta_copy: str = Field(..., description="Button/call-to-action text, e.g. Play Free Now")
    visual_prompt: str = Field(
        ...,
        description="One detailed sentence for AI image generation: subject, composition, mood, colors, style",
    )
    emotional_hook: str = Field(
        ...,
        description="Emotional driver: curiosity, FOMO, belonging, achievement, etc.",
    )
    urgency_element: Optional[str] = Field(
        None,
        description="Scarcity, limited time, or exclusivity if applicable",
    )
    ctr_rationale: str = Field(
        ...,
        description="2–3 sentences on why this concept can achieve 25%+ CTR",
    )
    recommended_sizes: List[str] = Field(
        default_factory=list,
        description="Recommended ad size names, e.g. medium_rectangle, leaderboard, facebook_landscape",
    )
    color_direction: Optional[str] = Field(
        None,
        description="Primary colors or palette for the banner",
    )


class BannerIdeationResult(BaseModel):
    """Full set of banner concepts for a brand or game."""

    entity_name: str = Field(..., description="Brand or game name")
    entity_type: str = Field(..., description="brand or game")
    concepts: List[BannerConcept] = Field(..., description="Banner concepts")
    primary_cta_theme: str = Field(
        ...,
        description="Overarching CTA theme across concepts",
    )
    size_recommendations: Optional[str] = Field(
        None,
        description="General guidance on which sizes to prioritize",
    )


class AdBannerIdeator:
    """Agent that creates high-converting ad banner concepts for brands and games."""

    def __init__(self, chat_model):
        self.chat_model = chat_model

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def ideate(
        self,
        brand_or_game: str,
        entity_type: Literal["brand", "game"] = "brand",
        entity_context: str = "",
        brief: str = "",
        audience: str = "General mobile and desktop users, 18–44",
        campaign_goal: str = "App installs / conversions",
        platforms: str = "Google Display, Meta (Facebook/Instagram), programmatic",
        trend_context: str = "",
        additional: str = "",
        num_concepts: int = 5,
    ) -> BannerIdeationResult:
        """
        Generate multiple high-converting ad banner concepts.

        Args:
            brand_or_game: Brand or game name
            entity_type: "brand" or "game"
            entity_context: Enriched S3 or user context (description, USPs, look and feel)
            brief: User brief or campaign brief
            audience: Target audience
            campaign_goal: Campaign objective
            platforms: Target ad platforms
            trend_context: Current trends to leverage (if trendy=True upstream)
            additional: Any extra instructions
            num_concepts: Number of concepts (min 3: creative, trend, high_converting)

        Returns:
            BannerIdeationResult with concepts and metadata
        """
        parser = PydanticOutputParser(pydantic_object=BannerIdeationResult)
        num_concepts = max(3, min(9, num_concepts))

        trend_block = trend_context if trend_context else "No specific trends provided; focus on evergreen hooks."
        entity_block = entity_context if entity_context else f"Promote {brand_or_game} with a focus on benefits and differentiation."

        messages = [
            SystemMessage(content=SYSTEM_PROMPT.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=HUMAN_PROMPT.format(
                    brand_or_game=brand_or_game,
                    entity_context=entity_block,
                    brief=brief or f"Create high-converting ad banners for {brand_or_game}.",
                    audience=audience,
                    campaign_goal=campaign_goal,
                    platforms=platforms,
                    trend_context=trend_block,
                    additional=additional or "None.",
                    num_concepts=num_concepts,
                )
            ),
        ]

        chain = self.chat_model | parser
        return await chain.ainvoke(messages)
