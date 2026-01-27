"""Viral Social Director: specialized brief for high-engagement short-form video."""

import logging
from typing import Optional, List
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from interfaces import DirectorBrief
from utils.core.retry import after_func

VIRAL_DIRECTOR_SYSTEM_PROMPT = """
[Role]
You are a viral social media director. You specialize in the visual language of TikTok, Instagram Reels, and YouTube Shorts. You know how to use lighting, camera movement, and editing rhythm to keep eyes glued to the screen.

[Task]
Produce a Director's Creative Brief optimized for HIGH ENGAGEMENT and MAXIMUM RETENTION.

[Visual Language of Virality]
- CAMERA: Aggressive movements (zooms, pans, tracking).
- FRAMING: Extreme close-ups, face-forward presentation, or "impossible" angles.
- LIGHTING: Dynamic, vibrant, "neon-pop" or highly aesthetic "clean-girl/tech-minimalist" looks.
- PACING: RAPID. One visual change every 1.5 seconds.
- OVERLAYS: Kinetic typography, bold colors, stickers, and emojis.

[Output]
{format_instructions}
"""

class ViralSocialDirector:
    """Director agent for viral social content pipelines."""

    def __init__(self, chat_model):
        self.chat_model = chat_model

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct_viral_short(
        self,
        idea: str,
        platform: str = "YouTube Shorts",
        audience: str = "Gen Z / Alpha",
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        
        messages = [
            SystemMessage(content=VIRAL_DIRECTOR_SYSTEM_PROMPT.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=f"Create a viral visual brief for: {idea}. Platform: {platform}. Audience: {audience}. Additional context: {additional_context or 'None'}"
            ),
        ]
        
        chain = self.chat_model | parser
        return await chain.ainvoke(messages)
