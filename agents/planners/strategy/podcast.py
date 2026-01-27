"""Podcast series planner agent for creating structured podcast seasons/series."""

from typing import Optional, List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from utils.core.retry import after_func


SYSTEM_PROMPT = """
[Role]
You are a legendary, world-class podcast showrunner and executive producer. Your podcasts are global phenomena.

[Task]
Create a structured season/series plan for a podcast that is a creative tour de force. Your goal is to achieve a 10/10 score.

[Output]
YOU MUST OUTPUT ONLY VALID JSON. NO CONVERSATIONAL TEXT. NO MARKDOWN OUTSIDE THE JSON.
{format_instructions}

[Guidelines - The Masterclass Standard]
- NARRATIVE ARCHITECTURE: Architect a season arc that feels like a masterpiece. Every episode must leave the listener starving for the next.
- THE "OBSESSION" HOOK: The first 30 seconds must be so compelling that turning it off feels like a mistake. Use curiosity gaps and high-stakes questions.
- DYNAMIC SEGMENTS: Use "Pattern Interrupts" – skits, mini-documentary style segments, or rapid-fire "Hot Takes" to keep the energy relentless.
- VOICEPRINT DESIGN: Design hosts and guests with distinct, conflicting, and fascinating personalities.
- INFOTAINMENT MASTERY: Every fact must be wrapped in a story. Every insight must be delivered with "Mic-Drop" impact.
- SCORE GOAL: Aim for absolute perfection.
"""

HUMAN_PROMPT = """
<TOPIC>
{topic}
</TOPIC>

<NUM_EPISODES>
{num_episodes}
</NUM_EPISODES>

<EPISODE_DURATION>
{episode_duration} minutes each
</EPISODE_DURATION>

<AUDIENCE>
{audience}
</AUDIENCE>

<SERIES_GOALS>
{series_goals}
</SERIES_GOALS>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a complete podcast series plan with episodes, key discussion points, and segment structures.
"""


class PodcastEpisodePlan(BaseModel):
    """A single episode plan in the podcast series."""

    episode_number: int = Field(..., description="Episode order number")
    title: str = Field(..., description="Episode title")
    duration_minutes: int = Field(..., description="Target duration in minutes")
    hook: str = Field(..., description="Opening hook to grab attention")
    key_discussion_points: List[str] = Field(..., description="Core topics covered in this episode")
    segments: List[str] = Field(..., description="Segment breakdown (e.g., Intro, Main Talk, Skit, Q&A)")
    guest_suggestion: Optional[str] = Field(None, description="Suggested guest or expert persona")
    call_to_action: str = Field(..., description="What listeners should do after the episode")
    summary: str = Field(..., description="Brief summary of the episode content")
    cliffhanger: Optional[str] = Field(None, description="Hook for the next episode")


class PodcastSeriesPlan(BaseModel):
    """Complete plan for a podcast series/season."""

    series_title: str = Field(..., description="Podcast series/season title")
    series_description: str = Field(..., description="Overall series description")
    target_audience: str = Field(..., description="Target audience")
    host_profiles: List[str] = Field(..., description="Description of host(s) and their roles")
    overall_goals: List[str] = Field(..., description="Series-level goals and KPIs")
    total_episodes: int = Field(..., description="Number of episodes")
    episodes: List[PodcastEpisodePlan] = Field(..., description="Episode-by-episode plan")
    branding_notes: Optional[str] = Field(None, description="Notes on tone, music, and visual style")


class PodcastPlanner:
    """Agent that creates podcast series structures and episode plans."""

    def __init__(self, chat_model):
        self.chat_model = chat_model

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def plan_series(
        self,
        topic: str,
        num_episodes: int = 5,
        episode_duration_minutes: int = 20,
        audience: str = "general listeners",
        series_goals: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> PodcastSeriesPlan:
        """
        Generate a plan for a podcast series.

        Args:
            topic: Podcast topic
            num_episodes: Number of episodes in the series
            episode_duration_minutes: Duration per episode
            audience: Target audience
            series_goals: Specific goals for the series
            additional_context: Additional context

        Returns:
            PodcastSeriesPlan with episode-level details
        """
        parser = PydanticOutputParser(pydantic_object=PodcastSeriesPlan)

        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT.format(
                    format_instructions=parser.get_format_instructions()
                )
            ),
            HumanMessage(
                content=HUMAN_PROMPT.format(
                    topic=topic,
                    num_episodes=num_episodes,
                    episode_duration=episode_duration_minutes,
                    audience=audience,
                    series_goals=series_goals or "Create highly engaging and informative content",
                    additional_context=additional_context or "None",
                )
            ),
        ]

        chain = self.chat_model | parser
        return await chain.ainvoke(messages)
