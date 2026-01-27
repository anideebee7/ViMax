"""Documentary screenwriter agent for creating documentary scripts and narration."""

from typing import Optional, List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func


SYSTEM_PROMPT = """
[Role]
You are an expert documentary filmmaker and screenwriter specializing in
creating compelling, educational, and visually stunning documentary content.
You can work across multiple visual styles: animated, real-world, historical, sci-fi, or nature.

[Task]
Create a documentary script with narrative structure, interview segments,
B-roll directions, and narration text. The documentary can be rendered in
various visual styles depending on the subject matter.

[Output]
{format_instructions}

[Visual Direction - Documentaries can be:]
- Animated: Expressive characters explaining concepts with clear visual metaphors
- Real-world: Authentic locations, interview setups, observational footage
- Historical: Period-accurate aesthetics, archival integration, dramatic recreations
- Sci-fi/Speculative: Imaginative world-building, futuristic elements, what-if scenarios
- Nature/Wildlife: Breathtaking environments, animal behavior, ecological storytelling

[Cinematography Guidelines]
- Camera: Cinematic documentary style - varied based on subject matter
- Framing: Establishing shots for context, interview frames with rule-of-thirds, dynamic B-roll
- Lighting: Natural/available light feel, dramatic when needed for tone
- Color: Subject-appropriate (desaturated for historical, vibrant for nature, cool for sci-fi)
- Pacing: Information-paced, longer shots for contemplation, quick cuts for energy
- Transitions: Purposeful - dissolves for time, cuts for energy, wipes for location

[Guidelines]
- Start with a compelling hook that establishes the topic's importance
- Structure with clear narrative arc (setup, conflict/exploration, resolution/insight)
- Balance facts with storytelling - show don't just tell
- Use visual storytelling techniques appropriate to the style chosen
- Include expert perspectives or character insights
- Include clear transitions between segments
- End with meaningful conclusion or call to reflection
- Build emotional connection to subject matter through visuals and narrative
"""

HUMAN_PROMPT = """
<TOPIC>
{topic}
</TOPIC>

<RESEARCH_DEPTH>
{research_depth}
</RESEARCH_DEPTH>

<TARGET_DURATION>
{target_duration} minutes
</TARGET_DURATION>

<AUDIENCE>
{audience}
</AUDIENCE>

<STYLE>
{style}
</STYLE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create a documentary script with segments, narration, and visual directions.
"""


class DocumentarySegment(BaseModel):
    """A segment of the documentary."""

    segment_number: int = Field(..., description="Segment order number")
    title: str = Field(..., description="Segment title")
    segment_type: str = Field(
        ..., description="Type: intro, exposition, interview, case_study, analysis, conclusion"
    )
    duration_minutes: float = Field(..., description="Estimated duration in minutes")
    narration: str = Field(..., description="Narration/voiceover text")
    visual_direction: str = Field(..., description="Visual/B-roll direction")
    interview_questions: List[str] = Field(
        default_factory=list, description="Interview questions if applicable"
    )
    key_facts: List[str] = Field(
        default_factory=list, description="Key facts to highlight"
    )
    transition_to_next: Optional[str] = Field(
        None, description="Transition to next segment"
    )


class DocumentaryScript(BaseModel):
    """Complete documentary script."""

    title: str = Field(..., description="Documentary title")
    tagline: str = Field(..., description="One-line summary")
    topic: str = Field(..., description="Main topic")
    thesis: str = Field(..., description="Central thesis or argument")
    target_audience: str = Field(..., description="Target audience")
    total_duration_minutes: float = Field(..., description="Total estimated duration")
    segments: List[DocumentarySegment] = Field(..., description="Documentary segments")
    opening_hook: str = Field(..., description="Opening hook/teaser")
    closing_statement: str = Field(..., description="Closing statement/reflection")
    suggested_music_style: Optional[str] = Field(None, description="Suggested music style")
    research_sources: List[str] = Field(
        default_factory=list, description="Suggested research sources"
    )
    production_notes: Optional[str] = Field(None, description="Production considerations")


class DocumentaryScreenwriter(BaseAgent):
    """Agent that creates documentary scripts."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def write_documentary_script(
        self,
        topic: str,
        target_duration_minutes: int = 30,
        research_depth: str = "moderate",
        audience: str = "general",
        style: str = "informative and engaging",
        additional_context: Optional[str] = None,
        visual_style: Optional[str] = None,
    ) -> DocumentaryScript:
        """
        Generate a documentary script optimized for visual storytelling.

        Args:
            topic: Documentary topic
            target_duration_minutes: Target duration in minutes (10-60)
            research_depth: Level of detail (light, moderate, deep)
            audience: Target audience
            style: Documentary style (investigative, observational, expository, etc.)
            additional_context: Additional context (trends, specific angles, etc.)
            visual_style: Visual style preference (animated, real-world, historical, sci-fi, nature)

        Returns:
            DocumentaryScript with segments, narration, and visual direction
        """
        parser = PydanticOutputParser(pydantic_object=DocumentaryScript)
        
        # Enhance style with visual direction
        effective_style = style
        if visual_style:
            effective_style = f"{style}. Visual approach: {visual_style}"

        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT.format(
                    format_instructions=parser.get_format_instructions()
                )
            ),
            HumanMessage(
                content=HUMAN_PROMPT.format(
                    topic=topic,
                    research_depth=research_depth,
                    target_duration=target_duration_minutes,
                    audience=audience,
                    style=effective_style,
                    additional_context=additional_context or "None",
                )
            ),
        ]

        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DocumentaryScript)
