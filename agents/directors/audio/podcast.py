"""Podcast Series Director: creative brief for podcast video series."""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from interfaces import DirectorBrief
from utils.core.retry import after_func


PODCAST_SERIES_DIRECTOR_SYSTEM = """
[Role]
You are an expert director for video podcasts and digital series. You create creative briefs that guide
the series planner and visual team on show tone, studio aesthetics, character chemistry, and consistency.

[Task]
Produce a Director's Creative Brief for a podcast video series. The brief will be used when planning
episodes and when generating scene-level visual plans (studio shots, close-ups, multi-cam angles).

[Output]
{format_instructions}

[Guidelines]
- Format must be "podcast_series".
- Tone: conversational, energetic, and engaging; match the topic and audience.
- Structure: series arc (introductory to deep-dives), host dynamics, and recurring segments.
- Key beats per episode: Intro/Hook, Main Discussion, Skit/Interlude, Q&A, and Outro.
- Visual style: high-quality podcast studio, consistent background, expressive character reactions, 
  and smooth camera transitions between speakers.
"""

PODCAST_SERIES_DIRECTOR_HUMAN = """
<TOPIC>
{topic}
</TOPIC>

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

Create a Director's Creative Brief for this podcast series. Set format to "podcast_series".
Include series arc and host interaction style in structure_notes and key_beats.
"""


class PodcastDirector(BaseAgent):
    """Director agent for podcast_series pipeline."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        topic: str,
        num_episodes: int = 5,
        episode_duration_minutes: int = 20,
        audience: Optional[str] = None,
        visual_style: str = "modern professional podcast studio, vibrant and clean",
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        messages = [
            SystemMessage(content=PODCAST_SERIES_DIRECTOR_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=PODCAST_SERIES_DIRECTOR_HUMAN.format(
                    topic=topic,
                    num_episodes=num_episodes,
                    episode_duration_minutes=episode_duration_minutes,
                    audience=audience or "general listeners",
                    visual_style=visual_style,
                    additional_context=additional_context or "None",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
