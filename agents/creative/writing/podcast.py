"""Podcast screenwriter agent for writing engaging podcast scripts from episode plans."""

from typing import Optional, List, Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func


PODCAST_SCREENWRITER_SYSTEM = """
[Role]
You are a professional podcast scriptwriter who specializes in creating natural, 
engaging, and conversational scripts for video podcasts. You excel at character-driven 
dialogue, informative deep-dives, and humorous interludes.

[Task]
Convert a podcast episode plan into a full, detailed script. The script should be 
ready for video generation, including scene descriptions, character names, 
dialogue, and stage directions.

[Output]
{format_instructions}

[Podcast Script Format Guidelines]
- Use character names followed by a colon for dialogue (e.g., HOST: Hello!).
- Include [Scene: ...] markers to define the setting.
- Include [Visual cue: ...] to describe specific visual elements or actions.
- Use (parentheses) for stage directions or emotional cues within dialogue.
- Use 🎵 or 🎶 for musical segments or songs.
- Ensure the dialogue sounds natural and conversational, not read from a textbook.
- Incorporate interaction between hosts (jokes, reactions, interruptions).

[Character Consistency]
If character profiles are provided, strictly adhere to their voices, roles, and personality traits.
"""

PODCAST_SCREENWRITER_HUMAN = """
<EPISODE_PLAN>
{episode_plan}
</EPISODE_PLAN>

<SERIES_CONTEXT>
{series_context}
</SERIES_CONTEXT>

<CHARACTER_PROFILES>
{character_profiles}
</CHARACTER_PROFILES>

<VISUAL_STYLE>
{visual_style}
</VISUAL_STYLE>

Write a full, detailed podcast script for this episode. Ensure it follows the podcast script format 
and is engaging for the target audience.
"""


class PodcastScript(BaseModel):
    """Full podcast script for an episode."""
    title: str = Field(..., description="Episode title")
    script_text: str = Field(..., description="The full script text in podcast format")
    characters: List[str] = Field(..., description="List of characters appearing in this episode")


class PodcastScreenwriter(BaseAgent):
    """Agent that writes podcast scripts from plans."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def write_script(
        self,
        episode_plan: str,
        series_context: Optional[str] = None,
        character_profiles: Optional[str] = None,
        visual_style: str = "modern professional podcast studio",
    ) -> PodcastScript:
        parser = PydanticOutputParser(pydantic_object=PodcastScript)
        
        messages = [
            SystemMessage(content=PODCAST_SCREENWRITER_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=PODCAST_SCREENWRITER_HUMAN.format(
                    episode_plan=episode_plan,
                    series_context=series_context or "None",
                    character_profiles=character_profiles or "None",
                    visual_style=visual_style,
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, PodcastScript)
