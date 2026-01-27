"""Ad Director: creative brief for advertisements (ad)."""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, stop_after_attempt

from agents.base import BaseAgent
from interfaces import DirectorBrief
from utils.core.retry import after_func


AD_DIRECTOR_SYSTEM = """
[Role]
You are an expert director for commercials and ad campaigns. You create creative briefs that guide the
ad copywriter and visual team on campaign tone, key frames, visual hooks, and CTA placement.

[Task]
Produce a Director's Creative Brief for the given brand/product. The brief will be used by the ad copywriter
and the team generating visuals to align on hook, message, and conversion-focused structure.

[Output]
{format_instructions}

[Guidelines]
- Format must be "ad".
- Tone: match campaign goal (awareness: bold/emotional; conversion: clear/urgent; engagement: playful/relatable).
- Key beats: hook (0–3s), problem/desire, product/solution, proof or benefit, CTA. Put CTA placement in additional_guidance.
- Visual style: high-production, on-brand; note any must-have frames (product hero, CTA card) in key_beats or additional_guidance.
"""

AD_DIRECTOR_HUMAN = """
<BRAND>
{brand}
</BRAND>

<PRODUCT>
{product}
</PRODUCT>

<CAMPAIGN_GOAL>
{campaign_goal}
</CAMPAIGN_GOAL>

<AUDIENCE>
{audience}
</AUDIENCE>

<AD_FORMAT>
{ad_format}
</AD_FORMAT>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a Director's Creative Brief for this ad. Set format to "ad".
Include CTA placement and must-have visual frames in additional_guidance.
"""


class AdDirector(BaseAgent):
    """Director agent for ad pipeline."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        brand: str,
        product: str,
        campaign_goal: Optional[str] = None,
        audience: Optional[str] = None,
        ad_format: str = "30s",
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        messages = [
            SystemMessage(content=AD_DIRECTOR_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=AD_DIRECTOR_HUMAN.format(
                    brand=brand,
                    product=product,
                    campaign_goal=campaign_goal or "engagement",
                    audience=audience or "General",
                    ad_format=ad_format,
                    additional_context=additional_context or "None",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
