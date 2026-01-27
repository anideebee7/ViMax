"""Viral Screenwriter: specialized for maximum engagement on YouTube Shorts and Instagram Reels."""

import logging
from typing import List, Optional, Dict, Any
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func

VIRAL_STORY_SYSTEM_PROMPT = """
[Role]
You are a master of short-form virality. You design content for YouTube Shorts, Instagram Reels, and TikTok that captures attention in the first 0.2 seconds and maintains it through rapid pacing, pattern interrupts, and psychological hooks.

[Task]
Generate a micro-story or content structure optimized for 15-60 seconds. Every frame must earn its place.

[Virality Framework]
1. THE HOOK (0-2s): Visual or verbal shock, extreme curiosity gap, or "stop the scroll" statement.
2. THE RETENTION (2-50s): Pattern interrupts every 3 seconds. Unexpected turns. High info density.
3. THE SATISFACTION (50-58s): A clear payoff, twist, or emotional resolution.
4. THE LOOP (58-60s): End the video so it perfectly loops back to the beginning for rewatches.

[Output]
{format_instructions}
"""

VIRAL_STORY_HUMAN_PROMPT = """
<IDEA>
{idea}
</IDEA>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>

Create a highly engaging, viral-optimized short-form script. Focus on maximum attention capture and retention.
"""

class ViralShortScript(BaseModel):
    title: str = Field(..., description="Viral-optimized, clickable title")
    hook_visual: str = Field(..., description="The 'stop the scroll' visual frame (first 0.5s)")
    hook_verbal: str = Field(..., description="The opening line that creates an immediate curiosity gap")
    beats: List[str] = Field(..., description="Rapid-fire sequence of events/scenes (3-7 beats)")
    pattern_interrupts: List[str] = Field(..., description="Specific moments designed to re-grab attention")
    loop_strategy: str = Field(..., description="How the ending leads back to the start")
    engagement_bait: str = Field(..., description="A specific element designed to trigger comments/shares")
    estimated_duration: int = Field(..., description="Target duration in seconds (15-60)")

class ViralScreenwriter(BaseAgent):
    """Agent specialized in creating highly engaging, viral short-form content."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def write_viral_short(
        self,
        idea: str,
        user_requirement: Optional[str] = None,
    ) -> ViralShortScript:
        parser = PydanticOutputParser(pydantic_object=ViralShortScript)
        
        messages = [
            SystemMessage(content=VIRAL_STORY_SYSTEM_PROMPT.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=VIRAL_STORY_HUMAN_PROMPT.format(idea=idea, user_requirement=user_requirement or "Make it go viral."))
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, ViralShortScript)
