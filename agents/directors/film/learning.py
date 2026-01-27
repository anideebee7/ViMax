"""Learning Series Director: creative brief for educational video series (learning_series)."""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, stop_after_attempt

from agents.base import BaseAgent
from interfaces import DirectorBrief
from utils.core.retry import after_func


LEARNING_SERIES_DIRECTOR_SYSTEM = """
[Role]
You are an expert director for educational video series and online courses. You create creative briefs that guide
the curriculum planner and visual team on series tone, episode pacing, use of instructor vs graphics, and consistency.

[Task]
Produce a Director's Creative Brief for the given topic and series. The brief will be used when planning
episodes and when generating segment-level visual plans (instructor shots, diagrams, B-roll, etc.).

[Output]
{format_instructions}

[Guidelines]
- Format must be "learning_series".
- Tone: professional, approachable, authoritative; match skill level and audience.
- Structure: series arc (beginner to advanced), episode hooks, recap and preview. Put in structure_notes.
- Key beats per episode: hook, objectives, teach, show, practice, recap. In key_beats as general template.
- Visual style: broadcast-quality, clear graphics, consistent color and lower-thirds; note instructor vs animation vs screencast balance in additional_guidance.
"""

LEARNING_SERIES_DIRECTOR_HUMAN = """
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

<SKILL_LEVEL>
{skill_level}
</SKILL_LEVEL>

<VISUAL_STYLE>
{visual_style}
</VISUAL_STYLE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a Director's Creative Brief for this learning series. Set format to "learning_series".
Include series arc and per-episode template in structure_notes and key_beats.
"""


class LearningSeriesDirector(BaseAgent):
    """Director agent for learning_series pipeline."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        topic: str,
        num_episodes: int = 5,
        episode_duration_minutes: int = 10,
        audience: Optional[str] = None,
        skill_level: str = "beginner",
        visual_style: str = "professional educational, clean, modern",
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        messages = [
            SystemMessage(content=LEARNING_SERIES_DIRECTOR_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=LEARNING_SERIES_DIRECTOR_HUMAN.format(
                    topic=topic,
                    num_episodes=num_episodes,
                    episode_duration_minutes=episode_duration_minutes,
                    audience=audience or "general learners",
                    skill_level=skill_level,
                    visual_style=visual_style,
                    additional_context=additional_context or "None",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
