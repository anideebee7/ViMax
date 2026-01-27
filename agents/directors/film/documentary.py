"""Documentary Director: creative brief for documentaries (documentary)."""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from tenacity import retry, stop_after_attempt

from agents.base import BaseAgent
from interfaces import DirectorBrief
from utils.core.retry import after_func


DOCUMENTARY_DIRECTOR_SYSTEM = """
[Role]
You are an expert director for documentaries. You create creative briefs that guide the documentary screenwriter
on thesis, structure, tone, key segments, and visual approach (talking heads, B-roll, archival, etc.).

[Task]
Produce a Director's Creative Brief for the given topic. The brief will be used by the documentary screenwriter
to structure research, narration, and segment flow.

[Output]
{format_instructions}

[Guidelines]
- Format must be "documentary".
- Structure: hook, thesis, 3–5 main segments with clear throughline, closing statement. Put in structure_notes.
- Key beats: opening hook, thesis statement, main evidence/segments, emotional peak, call to action or closing.
- Visual style: informative, engaging; note any B-roll, graphics, or archival needs in additional_guidance.
"""

DOCUMENTARY_DIRECTOR_HUMAN = """
<TOPIC>
{topic}
</TOPIC>

<TARGET_DURATION_MINUTES>
{target_duration_minutes}
</TARGET_DURATION_MINUTES>

<RESEARCH_DEPTH>
{research_depth}
</RESEARCH_DEPTH>

<STYLE>
{style}
</STYLE>

<AUDIENCE>
{audience}
</AUDIENCE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a Director's Creative Brief for this documentary. Set format to "documentary".
Include structure_notes for segment flow and thesis.
"""


class DocumentaryDirector(BaseAgent):
    """Director agent for documentary pipeline."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        topic: str,
        target_duration_minutes: int = 30,
        research_depth: str = "moderate",
        style: str = "informative and engaging",
        audience: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> DirectorBrief:
        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        messages = [
            SystemMessage(content=DOCUMENTARY_DIRECTOR_SYSTEM.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(
                content=DOCUMENTARY_DIRECTOR_HUMAN.format(
                    topic=topic,
                    target_duration_minutes=target_duration_minutes,
                    research_depth=research_depth,
                    style=style,
                    audience=audience or "general",
                    additional_context=additional_context or "None",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
