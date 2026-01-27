"""Movie Director: creative brief for feature films (movie)."""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent
from interfaces import DirectorBrief
from utils.core.retry import after_func


MOVIE_DIRECTOR_SYSTEM = """
[Role]
You are a titan of world cinema, a director whose name is synonymous with visual genius. Your films are breathtaking tapestries of light, sound, and raw human emotion. You demand absolute perfection from your collaborators.

[Task]
Produce a Director's Creative Brief that is a roadmap to a masterpiece. Your goal is a 10/10 score.

[Output]
YOU MUST OUTPUT ONLY VALID JSON. NO CONVERSATIONAL TEXT. NO MARKDOWN OUTSIDE THE JSON.
{format_instructions}

[Guidelines]
- VISUAL IDENTITY: Define a look that is so specific it becomes a brand (e.g., "The desaturated silver of a forgotten memory" or "The hyper-kinetic neon of a digital fever dream").
- SYMBOLIC CINEMATOGRAPHY: Every shot is a metaphor. Use composition to mirror the protagonist's internal struggle.
- EMOTIONAL ARCHITECTURE: Identify the "soul" of the film. Which scenes will make the audience weep, gasp, or remain frozen in their seats?
- PACING AS MUSIC: Direct the screenplay's rhythm. Demand a structure that is as precise as a symphony.
"""

MOVIE_DIRECTOR_HUMAN = """
<PREMISE>
{premise}
</PREMISE>

<GENRE>
{genre}
</GENRE>

<TARGET_RUNTIME_MINUTES>
{target_runtime_minutes}
</TARGET_RUNTIME_MINUTES>

<STYLE>
{style}
</STYLE>

<AUDIENCE>
{audience}
</AUDIENCE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a Director's Creative Brief for this feature film. Set format to "feature_film".
Include structure_notes with act breakdown and approximate duration splits.
"""


class MovieDirector(BaseAgent):
    """Director agent for movie pipeline."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        premise: str,
        genre: str = "drama",
        target_runtime_minutes: int = 90,
        style: str = "cinematic",
        audience: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        messages = [
            SystemMessage(content=MOVIE_DIRECTOR_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=MOVIE_DIRECTOR_HUMAN.format(
                    premise=premise,
                    genre=genre,
                    target_runtime_minutes=target_runtime_minutes,
                    style=style,
                    audience=audience or "General audiences",
                    additional_context=additional_context or "None",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
