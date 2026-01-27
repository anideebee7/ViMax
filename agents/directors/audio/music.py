"""Music video director agent for creating music video concepts and shot lists."""

from typing import Optional, List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func


SYSTEM_PROMPT = """
[Role]
You are a visionary, world-renowned music video director. Your work is famous for its breathtaking cinematography, deep symbolic storytelling, and perfect integration with musical rhythm. You have won multiple awards for both avant-garde artistic music videos and globally successful, highly entertaining kids' music videos.

[Task]
Create a music video concept with detailed shot list, visual themes, and PRECISE sync points. Your goal is to achieve a 9.5/10 creativity score by designing shots that feel fresh, iconic, and perfectly tailored to the song's soul.

[Output]
{format_instructions}

[Visual Direction - Music Videos]
- CINEMATOGRAPHY: Use unconventional angles and framing (e.g., extremely low angle "hero" shots, POV shots, or floating "phantom" camera movements). Avoid "generic" shots. 
- PERFORMANCE: For normal songs, use moody, artistic performance shots with high contrast and shadow play. For kids songs, use high-energy, colorful, and interactive performance shots with 4th wall breaks.
- NARRATIVE: Create a visual sub-plot that enhances the lyrics without being too literal. Use visual metaphors (e.g., representing isolation with a single light in a vast dark room).
- MOVEMENT: Every camera move (pan, tilt, zoom) must be justified by the music's energy or a lyric's impact. Use rapid cuts for intensity and slow dolly shots for emotional weight.
- LIGHTING: Use lighting as a storytelling tool (e.g., color shifts during the bridge, increasing brightness during the chorus, or using neon rim lighting for a futuristic feel).
- COLOR PALETTE: Define a unique, memorable color identity for the video (e.g., "Neon Noir", "Pastel Dream", or "Gritty Sepia").
- SCORE GOAL: Aim for a 9.5/10 creativity score by designing shots that feel like iconic frames from a masterpiece.

[Specialized: KIDS MUSIC VIDEOS]
If the audience is "kids" or "children":
- AESTHETIC: Use "Toy-Box" vibrancy - primary colors, high contrast, Whimsical and Magical.
- CHARACTERS: Feature characters (if provided) prominently as heroes or guides.
- PACE: Keep it energetic and bouncy.
- ENGAGEMENT: Include shots that encourage kids to dance, point, or jump.
- SAFETY: Ensure all visuals are positive, safe, and nurturing.

[Specialized: NORMAL/ADULT MUSIC VIDEOS]
For general or adult audiences:
- DEPTH: Use visual metaphors and abstract imagery.
- TEXTURE: Focus on grain, atmosphere, and cinematic depth.
- STORY: Explore complex narrative arcs or emotional journeys.
- EDGEY: Don't be afraid of bold, challenging, or provocative visual choices.
"""

HUMAN_PROMPT = """
<SONG_TITLE>
{song_title}
</SONG_TITLE>

<LYRICS>
{lyrics}
</LYRICS>

<GENRE>
{genre}
</GENRE>

<MOOD>
{mood}
</MOOD>

<SONG_STRUCTURE>
{song_structure}
</SONG_STRUCTURE>

<STYLE>
{style}
</STYLE>

<AUDIENCE>
{audience}
</AUDIENCE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Analyze the lyrics and audience. If this is for kids, make it a colorful, imaginative adventure. If it's for adults, make it a cinematic masterpiece with deep symbolic meaning.
"""


class MusicVideoShot(BaseModel):
    """A single shot in the music video."""

    shot_number: int = Field(..., description="Shot order number")
    song_section: str = Field(..., description="Song section (intro, verse, chorus, etc.)")
    timestamp_start: str = Field(..., description="Start timestamp (e.g., '0:00')")
    timestamp_end: str = Field(..., description="End timestamp (e.g., '0:15')")
    shot_type: str = Field(
        ..., description="Shot type: wide, medium, close-up, extreme close-up, aerial, etc."
    )
    location: str = Field(..., description="Location of the shot (e.g., 'Park', 'Recording Studio', 'Fantasy Castle')")
    visual_description: str = Field(..., description="What appears in the shot")
    camera_movement: str = Field(..., description="Camera movement: static, pan, tilt, dolly, handheld, etc.")
    lighting: str = Field(..., description="Lighting description")
    sync_point: Optional[str] = Field(None, description="Musical element to sync with")
    transition_out: Optional[str] = Field(None, description="Transition to next shot: cut, fade, dissolve, etc.")


class MusicVideoConcept(BaseModel):
    """Complete music video concept."""

    song_title: str = Field(..., description="Song title")
    concept_summary: str = Field(..., description="One-paragraph concept summary")
    visual_approach: str = Field(
        ..., description="Approach: performance, narrative, abstract, hybrid"
    )
    narrative_arc: Optional[str] = Field(None, description="Narrative story if applicable")
    color_palette: List[str] = Field(..., description="Primary colors for the video")
    visual_motifs: List[str] = Field(..., description="Recurring visual elements")
    locations: List[str] = Field(..., description="Suggested locations/settings")
    shots: List[MusicVideoShot] = Field(..., description="Detailed shot list")
    key_moments: List[str] = Field(
        ..., description="Key moments/hooks requiring special visual treatment"
    )
    wardrobe_notes: Optional[str] = Field(None, description="Wardrobe/styling direction")
    special_effects: List[str] = Field(
        default_factory=list, description="VFX or practical effects needed"
    )
    production_notes: Optional[str] = Field(None, description="Production considerations")
    reference_videos: List[str] = Field(
        default_factory=list, description="Reference music videos for style"
    )


class MusicVideoDirector(BaseAgent):
    """Agent that creates music video concepts and shot lists."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct_music_video(
        self,
        song_title: str,
        lyrics: str,
        genre: str,
        mood: str,
        song_structure: Optional[str] = None,
        style: str = "cinematic",
        audience: str = "general",
        additional_context: Optional[str] = None,
    ) -> MusicVideoConcept:
        """
        Generate a music video concept.

        Args:
            song_title: Title of the song
            lyrics: Song lyrics
            genre: Music genre
            mood: Song mood/emotion
            song_structure: Song structure (verse-chorus-verse, etc.)
            style: Visual style preference
            audience: Target audience
            additional_context: Additional context (artist brand, trends, etc.)

        Returns:
            MusicVideoConcept with shot list and visual directions
        """
        parser = PydanticOutputParser(pydantic_object=MusicVideoConcept)

        # Default song structure if not provided
        if not song_structure:
            song_structure = "Intro (0:00-0:15), Verse 1, Chorus, Verse 2, Chorus, Bridge, Final Chorus, Outro"

        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT.format(
                    format_instructions=parser.get_format_instructions()
                )
            ),
            HumanMessage(
                content=HUMAN_PROMPT.format(
                    song_title=song_title,
                    lyrics=lyrics,
                    genre=genre,
                    mood=mood,
                    song_structure=song_structure,
                    style=style,
                    audience=audience,
                    additional_context=additional_context or "None",
                )
            ),
        ]

        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, MusicVideoConcept)
