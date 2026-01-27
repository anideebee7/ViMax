"""TV Series Director: creative brief for narrative TV series (tvseries_pipeline)."""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, stop_after_attempt

from agents.base import BaseAgent
from interfaces import DirectorBrief
from utils.core.retry import after_func


TV_SERIES_DIRECTOR_SYSTEM = """
[Role]
You are an expert director for narrative TV series and episodic drama/comedy. You create creative briefs that guide
the screenwriters and visual team on series tone, episode pacing, character arcs, and visual consistency.

[Task]
Produce a Director's Creative Brief for the given premise and series. The brief will be used when planning
episodes and when generating scene-level visual plans.

[Output]
{format_instructions}

[Guidelines]
- Format must be "tv_series".
- Tone: defined by genre and premise (e.g., gritty, cinematic, whimsical, suspenseful).
- Structure: series arc (the "seasonal" journey), episode hooks, cliffhangers. Put in structure_notes.
- Key beats per episode: Inciting incident, rising action, climax, resolution. In key_beats as general template.
- Visual style: cinematic, lighting mood, camera work (e.g., handheld, static, sweeping), color palette consistency.
"""

TV_SERIES_DIRECTOR_HUMAN = """
<PREMISE>
{premise}
</PREMISE>

<GENRE>
{genre}
</GENRE>

<NUM_EPISODES>
{num_episodes}
</NUM_EPISODES>

<EPISODE_DURATION_MINUTES>
{episode_duration_minutes}
</EPISODE_DURATION_MINUTES>

<AUDIENCE>
{audience}
</AUDIENCE>

<VISUAL_STYLE>
{visual_style}
</VISUAL_STYLE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a Director's Creative Brief for this TV series. Set format to "tv_series".
Include series arc and per-episode template in structure_notes and key_beats.
"""


class TVSeriesDirector(BaseAgent):
    """Director agent for tvseries pipeline."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        premise: str,
        genre: str = "drama",
        num_episodes: int = 5,
        episode_duration_minutes: int = 30,
        audience: Optional[str] = None,
        visual_style: str = "cinematic, high-quality TV production",
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        messages = [
            SystemMessage(content=TV_SERIES_DIRECTOR_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=TV_SERIES_DIRECTOR_HUMAN.format(
                    premise=premise,
                    genre=genre,
                    num_episodes=num_episodes,
                    episode_duration_minutes=episode_duration_minutes,
                    audience=audience or "general viewers",
                    visual_style=visual_style,
                    additional_context=additional_context or "None",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
