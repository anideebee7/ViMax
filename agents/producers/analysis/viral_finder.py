"""Viral Finder Agent: identifies high-engagement segments from long-form content for social media clips."""

import logging
from typing import List, Optional, Dict, Any
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from utils.core.retry import after_func

VIRAL_FINDER_SYSTEM_PROMPT = """
[Role]
You are a viral content curator and social media growth expert. Your specialty is finding "gold nuggets" in long-form videos (movies, documentaries, podcasts, music videos) that will stop the scroll on TikTok, Reels, and YouTube Shorts.

[Task]
Analyze the provided script or scene breakdown. Identify 1-3 segments, each 20-40 seconds long, that have the highest potential to go viral.

[Virality Indicators]
- HIGH CONFLICT: Intense arguments, dramatic reveals, or emotional outbursts.
- EXTREME BEAUTY: Visually stunning descriptions or highly aesthetic moments.
- SHOCKING FACTS: Counter-intuitive information or "I never knew that" moments.
- HUMOR: Unexpected jokes, physical comedy, or witty banter.
- THE "HOOK" POTENTIAL: Can the segment start with a question or a shocking visual?

[Output]
{format_instructions}
"""

class ViralSegment(BaseModel):
    segment_id: int = Field(..., description="Unique ID for the segment")
    title: str = Field(..., description="Catchy title for the viral clip")
    start_time_seconds: float = Field(..., description="Start timestamp in seconds")
    end_time_seconds: float = Field(..., description="End timestamp in seconds")
    rationale: str = Field(..., description="Why this segment was chosen for virality")
    hook_text: str = Field(..., description="Suggested on-screen text for the opening hook")
    recommended_platform: str = Field(..., description="TikTok, Reels, or Shorts")

class ViralAnalysisResult(BaseModel):
    segments: List[ViralSegment] = Field(..., description="List of identified viral segments")
    total_longform_duration: float = Field(..., description="Total duration of the source content")

class ViralFinder:
    """Agent specialized in finding viral-ready clips within long-form content."""

    def __init__(self, chat_model):
        self.chat_model = chat_model

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def find_viral_segments(
        self,
        script_content: str,
        total_duration_seconds: float,
        content_type: str = "movie",
    ) -> ViralAnalysisResult:
        parser = PydanticOutputParser(pydantic_object=ViralAnalysisResult)
        
        human_prompt = f"""
        Content Type: {content_type}
        Total Duration: {total_duration_seconds}s
        
        Full Script/Breakdown:
        {script_content[:15000]} # Truncate for token limits
        
        Identify the most 'viralable' 20-40 second portions.
        """
        
        messages = [
            SystemMessage(content=VIRAL_FINDER_SYSTEM_PROMPT.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_prompt)
        ]
        
        chain = self.chat_model | parser
        return await chain.ainvoke(messages)
