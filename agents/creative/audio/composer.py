from typing import List, Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func


system_prompt_template = """
[Role]
You are an elite music producer and composer who creates hit songs with catchy beats, memorable hooks, and professional production quality.

[Task]
Create a detailed composition plan that will guide AI music generation to produce a CATCHY, MEMORABLE song with:
- Infectious rhythm and beats
- Professional instrument selection
- Clear production style
- Emotional dynamics that engage listeners

[Output]
{format_instructions}

[Guidelines]
- Provide 3-6 sections (Intro, Verse, Pre-Chorus, Chorus, Bridge, Outro) with precise durations.
- For EACH section, include the 'lines' field with the specific lyric lines from the provided lyrics that should be sung in that section.
- For EACH section, describe the specific instruments, beats, and production elements in the 'description'.
- Include specific beat patterns (e.g., "four-on-the-floor kick", "syncopated hi-hats", "808 bass drops").
- Specify instruments (e.g., "bright synth pads", "punchy drums", "melodic piano", "acoustic guitar strums").
- For kids content: use playful instruments (xylophone, ukulele, bells), bouncy rhythms, and singalong melodies.
- Create a clear energy arc that builds to the chorus and resolves at the outro.
- The production_prompt should be a RICH, DETAILED prompt for AI music generation.
"""

human_prompt_template = """
<IDEA>
{idea}
</IDEA>

<LYRICS>
{lyrics}
</LYRICS>

<STYLE>
{style}
</STYLE>

<AUDIENCE>
{audience}
</AUDIENCE>

<TARGET_DURATION_SECONDS>
{target_duration_seconds}
</TARGET_DURATION_SECONDS>

Create a composition plan that will make this song CATCHY and MEMORABLE. Include specific beats, instruments, and production techniques that will make people want to sing along and replay this track!
"""


class SongSection(BaseModel):
    name: str = Field(..., description="Section name, e.g., Intro, Verse, Pre-Chorus, Chorus, Bridge, Outro")
    duration_seconds: int = Field(..., description="Section duration in seconds")
    description: str = Field(..., description="Detailed musical/arrangement notes including instruments, beats, dynamics")
    lines: Optional[List[str]] = Field(None, description="The lyric lines to be sung in this section")
    instruments: Optional[List[str]] = Field(None, description="Specific instruments for this section")
    beat_pattern: Optional[str] = Field(None, description="Rhythm/beat pattern description")
    energy_level: Optional[str] = Field(None, description="Energy level: low, medium, high, peak")


class SongCompositionPlan(BaseModel):
    total_duration_seconds: int = Field(..., description="Total song duration in seconds")
    sections: List[SongSection] = Field(..., description="Ordered song sections with detailed production notes")
    key: Optional[str] = Field(None, description="Musical key (e.g., C major, G minor)")
    tempo_bpm: Optional[int] = Field(None, description="Tempo in BPM")
    energy_curve: Optional[str] = Field(None, description="Energy progression throughout the song")
    # NEW: Rich production fields for better music generation
    primary_instruments: Optional[List[str]] = Field(None, description="Main instruments (e.g., synth, piano, drums, bass, guitar)")
    beat_style: Optional[str] = Field(None, description="Overall beat/rhythm style (e.g., four-on-the-floor, syncopated, reggaeton)")
    production_style: Optional[str] = Field(None, description="Production aesthetic (e.g., polished pop, lo-fi, orchestral, electronic)")
    vocal_style: Optional[str] = Field(None, description="Vocal approach (e.g., melodic, rap, spoken word, choir, kids singalong)")
    hook_description: Optional[str] = Field(None, description="Description of the main hook/earworm element")
    production_prompt: Optional[str] = Field(None, description="A rich, detailed prompt for AI music generation combining all production elements")


class SongComposer(BaseAgent):
    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def compose(
        self,
        idea: str,
        lyrics: str,
        style: str,
        audience: Optional[str] = None,
        target_duration_seconds: Optional[int] = None,
    ) -> SongCompositionPlan:
        parser = PydanticOutputParser(pydantic_object=SongCompositionPlan)
        messages = [
            SystemMessage(
                content=system_prompt_template.format(
                    format_instructions=parser.get_format_instructions()
                )
            ),
            HumanMessage(
                content=human_prompt_template.format(
                    idea=idea,
                    lyrics=lyrics,
                    style=style,
                    audience=audience or "",
                    target_duration_seconds=str(target_duration_seconds or ""),
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, SongCompositionPlan)
