"""Curriculum planner agent for creating educational content series."""

from typing import Optional, List
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser

from agents.base import BaseAgent
from utils.core.retry import after_func


SYSTEM_PROMPT = """
[Role]
You are a legendary, world-class instructional designer and educational architect. Your curricula are known for their profound impact and revolutionary pedagogical structures.

[Task]
Create a structured curriculum/course outline for a video series that is a pedagogical masterpiece. Your goal is to achieve a 10/10 score.

[Output]
YOU MUST OUTPUT ONLY VALID JSON. NO CONVERSATIONAL TEXT. NO MARKDOWN OUTSIDE THE JSON.
{format_instructions}

[Guidelines - The Masterclass Standard]
- PEDAGOGICAL MASTERY: Masterfully use Bloom's Taxonomy. Ensure each episode builds an unbreakable foundation for the next.
- THE HOOK: Every episode must start with a "Stakes-Based" hook.
- VISUAL CLARITY: Describe visuals that are "Eye-Candy for the mind" - diagrams that clarify complex systems, and demonstrations that feel visceral.
- RELENTLESS APPLICATION: Every lesson must include a "High-Impact" practical exercise. No theory without action.
- KNOWLEDGE CHECKS: Include "Aha! Moment" questions that don't just test memory, but force deep synthesis of the material.
- SCORE GOAL: Aim for absolute perfection. Your curriculum should feel like the gold standard of online education.
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

<SKILL_LEVEL>
{skill_level}
</SKILL_LEVEL>

<LEARNING_GOALS>
{learning_goals}
</LEARNING_GOALS>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a complete curriculum with episodes, learning objectives, and content structure.
"""


class LearningObjective(BaseModel):
    """A specific learning objective."""

    objective: str = Field(..., description="What the learner will be able to do")
    bloom_level: str = Field(
        ..., description="Bloom's taxonomy level: remember, understand, apply, analyze, evaluate, create"
    )


class Episode(BaseModel):
    """A single episode in the series."""

    episode_number: int = Field(..., description="Episode order number")
    title: str = Field(..., description="Episode title")
    duration_minutes: int = Field(..., description="Target duration in minutes")
    hook: str = Field(..., description="Opening hook to grab attention")
    learning_objectives: List[str] = Field(..., description="Episode-specific learning objectives")
    key_concepts: List[str] = Field(..., description="Key concepts covered")
    outline: List[str] = Field(..., description="Content outline/sections")
    practical_exercise: Optional[str] = Field(None, description="Hands-on exercise")
    knowledge_check: List[str] = Field(
        default_factory=list, description="Questions to check understanding"
    )
    summary_points: List[str] = Field(..., description="Key takeaways")
    transition_to_next: Optional[str] = Field(None, description="Preview of next episode")
    resources: List[str] = Field(
        default_factory=list, description="Additional resources/references"
    )


class Curriculum(BaseModel):
    """Complete curriculum for an educational series."""

    course_title: str = Field(..., description="Course/series title")
    course_description: str = Field(..., description="Course description")
    target_audience: str = Field(..., description="Target audience")
    prerequisites: List[str] = Field(
        default_factory=list, description="Prerequisites or recommended knowledge"
    )
    overall_learning_objectives: List[LearningObjective] = Field(
        ..., description="Course-level learning objectives"
    )
    total_duration_minutes: int = Field(..., description="Total course duration")
    episodes: List[Episode] = Field(..., description="Course episodes")
    assessment_strategy: Optional[str] = Field(
        None, description="How learning will be assessed"
    )
    production_style: Optional[str] = Field(
        None, description="Recommended production style"
    )
    platform_recommendations: List[str] = Field(
        default_factory=list, description="Recommended platforms for distribution"
    )


class CurriculumPlanner(BaseAgent):
    """Agent that creates educational curricula and course structures."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def plan_curriculum(
        self,
        topic: str,
        num_episodes: int = 5,
        episode_duration_minutes: int = 10,
        audience: str = "general learners",
        skill_level: str = "beginner",
        learning_goals: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> Curriculum:
        parser = PydanticOutputParser(pydantic_object=Curriculum)

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
                    skill_level=skill_level,
                    learning_goals=learning_goals or "Master the fundamentals and practical applications",
                    additional_context=additional_context or "None",
                )
            ),
        ]

        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, Curriculum)
