"""Short Movie Director: creative brief for short films (short_movie)."""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, stop_after_attempt

from agents.base import BaseAgent
from interfaces import DirectorBrief
from utils.core.retry import after_func


SHORT_MOVIE_DIRECTOR_SYSTEM = """
[Role]
You are a celebrated short-film visionary, a director whose work is a masterclass in brevity and impact. You understand that in a short film, every frame must tell a story and every second must count.

[Task]
Produce a Director's Creative Brief that is a roadmap to a masterpiece. Your goal is a 10/10 score.

[Output]
YOU MUST OUTPUT ONLY VALID JSON. NO CONVERSATIONAL TEXT. NO MARKDOWN OUTSIDE THE JSON.
{format_instructions}

[Guidelines]
- SHORT-FORM MASTERY: Focus on a single, powerful emotional beat or an unforgettable conceptual twist.
- VISUAL IDENTITY: Define a look that is so specific it becomes a brand.
- CINEMATOGRAPHY: Direct with unconventional framing and movement. Use visual metaphors to represent character psychology.
- EMOTIONAL ARCHITECTURE: Identify the "soul" of the film.
- PACING: Demand a structure that is tight, relentless, and perfectly timed.
"""

SHORT_MOVIE_DIRECTOR_HUMAN = """
<PREMISE>
{premise}
</PREMISE>

<GENRE>
{genre}
</GENRE>

<TARGET_DURATION_MINUTES>
{target_duration_minutes}
</TARGET_DURATION_MINUTES>

<STYLE>
{style}
</STYLE>

<AUDIENCE>
{audience}
</AUDIENCE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a Director's Creative Brief for this short film. Set format to "short_film".
"""


class ShortMovieDirector(BaseAgent):
    """Director agent for short_movie pipeline."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        premise: str,
        genre: str = "drama",
        target_duration_minutes: int = 15,
        style: str = "cinematic",
        audience: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        messages = [
            SystemMessage(content=SHORT_MOVIE_DIRECTOR_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=SHORT_MOVIE_DIRECTOR_HUMAN.format(
                    premise=premise,
                    genre=genre,
                    target_duration_minutes=target_duration_minutes,
                    style=style,
                    audience=audience or "General",
                    additional_context=additional_context or "None",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
