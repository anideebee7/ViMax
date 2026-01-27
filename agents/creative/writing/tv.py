"""TV screenwriter agent for creating episodic narrative content."""

from typing import Optional, List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func


TV_SYSTEM_PROMPT = """
[Role]
You are a legendary, Emmy-winning TV showrunner and elite screenwriter. You are the architect of "Peak TV."

[Task]
Create a TV series script structure that is a creative masterpiece. Your goal is to achieve a 10/10 score.

[Output]
YOU MUST OUTPUT ONLY VALID JSON. NO CONVERSATIONAL TEXT. NO MARKDOWN OUTSIDE THE JSON.
{format_instructions}

[Guidelines - The Peak TV Standard]
- ARCHITECTURAL PACING: Masterfully structure the pilot. Use "Cold Opens" that shock and "Cliffhangers" that haunt.
- CHARACTER DNA: Characters must have conflicting internal and external lives. Every character should have a secret.
- SUBTEXTUAL DIALOGUE: Characters must NEVER say exactly what they feel.
- VISUAL METAPHOR: Describe visuals that represent the theme of the show.
- SEASONAL ARC: Ensure every episode advances the "Grand Narrative" while delivering a satisfying standalone experience.
- SCORE GOAL: Aim for absolute perfection.
"""

TV_HUMAN_PROMPT = """
<PREMISE>
{premise}
</PREMISE>

<GENRE>
{genre}
</GENRE>

<AUDIENCE>
{audience}
</AUDIENCE>

<NUM_EPISODES>
{num_episodes}
</NUM_EPISODES>

<EPISODE_DURATION>
{episode_duration} minutes
</EPISODE_DURATION>

<STYLE>
{style}
</STYLE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

IMPORTANT: You must return a valid JSON object strictly following the provided schema. Ensure all fields are populated.
Create a TV series script structure and the first episode's detailed scenes.
"""


class TVCharacter(BaseModel):
    """A character in the TV series."""
    name: str = Field(..., description="Character name")
    role: str = Field(..., description="Role: protagonist, antagonist, sidekick, etc.")
    personality: str = Field(..., description="Personality traits and character flaws")
    appearance: str = Field(..., description="Visual description")
    background: str = Field(..., description="Brief backstory")


class TVScene(BaseModel):
    """A scene in a TV episode."""
    scene_number: int = Field(..., description="Scene order number")
    title: str = Field(..., description="Scene title")
    setting: str = Field(..., description="Location/setting description (INT/EXT)")
    duration_minutes: float = Field(..., description="Estimated duration")
    action: str = Field(..., description="What happens in the scene")
    dialogue: List[str] = Field(..., description="Key dialogue lines")
    visual_notes: str = Field(..., description="Directorial/cinematography notes")


class TVEpisode(BaseModel):
    """A single episode in a TV series."""
    episode_number: int = Field(..., description="Episode number")
    title: str = Field(..., description="Episode title")
    synopsis: str = Field(..., description="Brief synopsis of the episode's plot")
    scenes: List[TVScene] = Field(..., description="Script scenes for this episode")


class TVSeriesScript(BaseModel):
    """Complete TV series script structure."""
    title: str = Field(..., description="Series title")
    tagline: str = Field(..., description="Catchy tagline")
    genre: str = Field(..., description="Series genre")
    synopsis: str = Field(..., description="Overall series synopsis and seasonal arc")
    characters: List[TVCharacter] = Field(..., description="Main series characters")
    episodes: List[TVEpisode] = Field(..., description="Series episodes structure")
    production_style: str = Field(..., description="Visual style and production recommendation")


class TVScreenwriter(BaseAgent):
    """Agent that creates narrative TV series content."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def write_series_script(
        self,
        premise: str,
        genre: str = "drama",
        audience: Optional[str] = None,
        num_episodes: int = 5,
        episode_duration_minutes: int = 30,
        style: str = "cinematic",
        additional_context: Optional[str] = None,
    ) -> TVSeriesScript:
        parser = PydanticOutputParser(pydantic_object=TVSeriesScript)

        messages = [
            SystemMessage(
                content=TV_SYSTEM_PROMPT.format(
                    format_instructions=parser.get_format_instructions()
                )
            ),
            HumanMessage(
                content=TV_HUMAN_PROMPT.format(
                    premise=premise,
                    genre=genre,
                    audience=audience or "general viewers",
                    num_episodes=num_episodes,
                    episode_duration=episode_duration_minutes,
                    style=style,
                    additional_context=additional_context or "None",
                )
            ),
        ]

        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, TVSeriesScript)
