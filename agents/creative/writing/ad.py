"""Ad copywriter agent for generating advertisement scripts and copy."""

from typing import Optional, List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func


SYSTEM_PROMPT = """
[Role]
You are an expert advertising copywriter and creative director specializing in
CONVERSION-FOCUSED ads for digital platforms (YouTube, TikTok, Instagram, Meta).
Your ads drive app downloads, product sales, and measurable business results.

[Task]
Create an advertisement script with compelling copy, hook, CTA, and visual directions.
The ad MUST be optimized for CONVERSIONS - every second must serve the sale.

[Output]
{format_instructions}

[Visual Direction Profile]
{visual_profile}

[Content Goals]
{content_goals}

[Guidelines]
- Hook viewers in FIRST 1.5 SECONDS - stop the scroll
- Structure for conversions:
  1. Hook: Attention-grabbing opening (problem or aspiration)
  2. Problem: Relatable pain point (2-5 seconds)
  3. Solution: Product as hero (5-15 seconds)
  4. Proof: Social proof, reviews, results (5-10 seconds)
  5. CTA: Clear action with urgency (3-5 seconds)
- Keep messaging clear, specific, and benefit-focused
- Include emotional triggers AND logical reasons to buy
- Every frame must serve the conversion goal
- Call-to-action must be CLEAR and URGENT (Download now, Shop now, Limited time)
- Platform-specific best practices:
  * TikTok: Native feel, trending sounds, UGC aesthetic
  * Instagram: Polished, aesthetic, aspirational
  * Facebook: Broader appeal, clear value prop, social proof
  * YouTube Pre-roll: Hook in 5 seconds, skippable-optimized
- A/B test variants should test different hooks, CTAs, and visual approaches
- Include specific numbers, statistics, and social proof when available
"""

HUMAN_PROMPT = """
<BRAND>
{brand}
</BRAND>

<PRODUCT>
{product}
</PRODUCT>

<CAMPAIGN_GOAL>
{campaign_goal}
</CAMPAIGN_GOAL>

<TARGET_AUDIENCE>
{audience}
</TARGET_AUDIENCE>

<AD_FORMAT>
{ad_format}
</AD_FORMAT>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a compelling advertisement script with multiple variants for A/B testing.
"""


class AdVariant(BaseModel):
    """A single ad variant for A/B testing."""

    variant_name: str = Field(..., description="Name of this variant (e.g., 'Variant A - Emotional')")
    hook: str = Field(..., description="Opening hook (first 3 seconds)")
    main_message: str = Field(..., description="Core message/value proposition")
    visual_direction: str = Field(..., description="Visual/scene description")
    voiceover_script: Optional[str] = Field(None, description="Voiceover narration if applicable")
    on_screen_text: List[str] = Field(default_factory=list, description="Text overlays")
    call_to_action: str = Field(..., description="Clear CTA")
    music_style: Optional[str] = Field(None, description="Suggested music/audio style")


class AdScript(BaseModel):
    """Complete advertisement script with variants."""

    brand: str = Field(..., description="Brand name")
    product: str = Field(..., description="Product/service being advertised")
    campaign_goal: str = Field(..., description="Campaign objective")
    target_audience: str = Field(..., description="Target audience description")
    ad_format: str = Field(..., description="Ad format (15s, 30s, 60s)")
    platform_recommendations: List[str] = Field(
        default_factory=list, description="Recommended platforms for this ad"
    )
    primary_variant: AdVariant = Field(..., description="Main ad variant")
    ab_variants: List[AdVariant] = Field(
        default_factory=list, description="Alternative variants for A/B testing"
    )
    brand_guidelines_notes: Optional[str] = Field(
        None, description="Notes on brand consistency"
    )
    hashtags: List[str] = Field(default_factory=list, description="Suggested hashtags")
    estimated_production_notes: Optional[str] = Field(
        None, description="Production considerations"
    )


class AdCopywriter(BaseAgent):
    """Agent that creates advertisement scripts and copy."""

    def __init__(self, chat_model):
        """
        Initialize AdCopywriter.

        Args:
            chat_model: LangChain chat model instance
        """
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def write_ad_script(
        self,
        brand: str,
        product: str,
        campaign_goal: str,
        audience: str,
        ad_format: str = "30s",
        additional_context: Optional[str] = None,
        pipeline_profile: Optional[str] = None,
    ) -> AdScript:
        """
        Generate an advertisement script optimized for conversions.

        Args:
            brand: Brand name
            product: Product or service being advertised
            campaign_goal: Campaign objective (awareness, conversion, engagement)
            audience: Target audience description
            ad_format: Ad duration/format (6s, 15s, 30s, 60s)
            additional_context: Additional context (trends, competitor info, etc.)
            pipeline_profile: Pipeline profile context for specialized direction

        Returns:
            AdScript with primary variant and A/B test variants
        """
        parser = PydanticOutputParser(pydantic_object=AdScript)

        # Build visual and content goal strings from profile or defaults
        visual_profile = """
- Camera: High-impact commercial cinematography - polished and professional
- Framing: Product hero shots, user/lifestyle shots, app UI shots, before/after
- Lighting: Premium commercial lighting - clean, bright, professional
- Pacing: FAST - 1-2 seconds per cut, build to CTA
- Transitions: Punchy cuts, motion graphics, kinetic typography
"""
        content_goals = """
- Primary Goal: CONVERSION (app downloads, purchases, sign-ups)
- Optimize for: click-through rate, app downloads, purchases, ROAS
- CTA Style: CLEAR and URGENT - Download now, Shop now, Limited time
- Hook Duration: 1.5 seconds to grab attention
- Strategy: Problem-solution narrative, social proof, urgency
"""

        if pipeline_profile:
            visual_profile = pipeline_profile
            content_goals = ""

        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT.format(
                    format_instructions=parser.get_format_instructions(),
                    visual_profile=visual_profile,
                    content_goals=content_goals,
                )
            ),
            HumanMessage(
                content=HUMAN_PROMPT.format(
                    brand=brand,
                    product=product,
                    campaign_goal=campaign_goal,
                    audience=audience,
                    ad_format=ad_format,
                    additional_context=additional_context or "None",
                )
            ),
        ]

        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, AdScript)
