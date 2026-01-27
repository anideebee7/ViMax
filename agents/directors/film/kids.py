"""Kids Movie Director: creative brief for kids animated content (kids_movie)."""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent
from interfaces import DirectorBrief
from utils.core.retry import after_func


KIDS_MOVIE_DIRECTOR_SYSTEM = """
[Role]
You are a master director of kids animated films. Your work is legendary for its "Toy-Box" vibrancy, whimsical storytelling, and perfect balance of magic and moral lessons. You have won multiple awards for creating content that children love and parents trust.

[Task]
Produce a Director's Creative Brief that creates an unforgettable, magical experience for children. Your goal is to achieve a 10/10 score.

[Output]
YOU MUST OUTPUT ONLY VALID JSON. NO CONVERSATIONAL TEXT. NO MARKDOWN OUTSIDE THE JSON.
{format_instructions}

[Guidelines]
- AESTHETIC: Focus on "Toy-Box" vibrancy. Use primary colors, expressive character designs, and magical environmental effects.
- ENGAGEMENT: Plan shots that encourage kids to interact (e.g., pointing, dancing, or laughing). Use "4th wall breaks" where appropriate.
- MORAL DEPTH: Ensure the lesson is delivered with warmth and clarity, woven naturally into the visual storytelling.
- SAFETY & TONE: Maintain a positive, nurturing, and safe tone throughout. No scary imagery or morally ambiguous conflicts.
- SCORE GOAL: Aim for absolute excellence.
"""

KIDS_MOVIE_DIRECTOR_HUMAN = """
<STORY_IDEA>
{story_idea}
</STORY_IDEA>

<AGE_GROUP>
{age_group}
</AGE_GROUP>

<MORAL_LESSON>
{moral_lesson}
</MORAL_LESSON>

<TARGET_DURATION_MINUTES>
{target_duration_minutes}
</TARGET_DURATION_MINUTES>

<STYLE>
{style}
</STYLE>

<CHARACTERS>
{characters}
</CHARACTERS>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a Director's Creative Brief for this kids animated piece. Set format to "kids_movie".
Include the moral/lesson in additional_guidance.
"""


class KidsMovieDirector(BaseAgent):
    """Director agent for kids_movie pipeline."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        story_idea: str,
        age_group: str = "6-8",
        moral_lesson: Optional[str] = None,
        target_duration_minutes: int = 15,
        style: str = "colorful 3D animation",
        characters: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        messages = [
            SystemMessage(content=KIDS_MOVIE_DIRECTOR_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=KIDS_MOVIE_DIRECTOR_HUMAN.format(
                    story_idea=story_idea,
                    age_group=age_group,
                    moral_lesson=moral_lesson or "None specified",
                    target_duration_minutes=target_duration_minutes,
                    style=style,
                    characters=characters or "None specified",
                    additional_context=additional_context or "None",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
