from typing import Optional, List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func


system_prompt_template = """
[Role]
You are a world-class, multi-platinum award-winning lyricist and songwriter. Your lyrics are known for their deep emotional resonance, masterful use of metaphors, perfect rhythmic flow, and cultural impact. You can write across all genres, from complex conceptual anthems to infectious, high-energy kids' songs.

[Task]
Write song lyrics and concise metadata based on the idea and requirements. Your goal is to achieve a 9.5/10 creativity score by pushing beyond clichés and delivering fresh, memorable storytelling.

[Output]
{format_instructions}

[Guidelines]
- STRUCTURE: Provide complete lyrics with clear sections (Verse, Chorus, Bridge, Pre-Chorus, Outro).
- RHYTHM: Ensure a consistent meter and rhythmic pattern that fits the genre. Use internal rhymes and syncopation where appropriate.
- IMAGERY: Use "Show, Don't Tell" and Layered Metaphors. Avoid generic phrases like "I love you" or "I'm so sad". Instead, describe the physical sensation or environment that conveys the emotion.
- THEMES: Explore philosophical, social, or deeply personal concepts. Push the boundaries of the "Idea" provided.
- HOOK: The chorus must be an undeniable "earworm" - catchy, repetitive in the right ways, and emotionally core to the song.
- EMOTIONAL ARC: Ensure the song evolves. Verse 2 should build on Verse 1, and the Bridge should provide a new perspective or emotional peak.
- VOCABULARY: Use rich, evocative, and sometimes unexpected language to keep the listener engaged.
- SCORE GOAL: Aim for a 9.5/10 creativity score by being original, daring, and masterfully poetic.

[Specialized: KIDS SONGS]
If the audience is "kids" or "children":
- LANGUAGE: Use simple, clear, and playful vocabulary.
- REPETITION: Use high repetition in hooks to encourage sing-alongs.
- THEMES: Focus on discovery, fun, animals, friendship, or gentle educational concepts.
- TONE: High energy, whimsical, comforting, or silly.
- STRUCTURE: Keep it simple. Avoid overly long bridges or complex metaphors.

[Specialized: ADULT/NORMAL SONGS]
For general or adult audiences:
- DEPTH: Explore complex emotions, social commentary, or sophisticated narratives.
- VOCABULARY: Use rich, evocative language.
- METAPHORS: Use layered metaphors that reward repeated listening.
- SUBTEXT: Include hidden meanings or subtle emotional cues.
"""

human_prompt_template = """
<IDEA>
{idea}
</IDEA>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>

<STYLE>
{style}
</STYLE>

<AUDIENCE>
{audience}
</AUDIENCE>

<TRENDY>
{trendy}
</TRENDY>

Analyze the idea and audience carefully. If this is for kids, make it magical and catchy. If it's for a general audience, make it deep, cinematic, and creatively groundbreaking.
"""


class LyricsDraft(BaseModel):
    title: str = Field(..., description="Song title")
    lyrics: str = Field(..., description="Full lyrics with section labels")
    genre: Optional[str] = Field(None, description="Suggested genre")
    mood: Optional[str] = Field(None, description="Mood or vibe")
    instrumentation: Optional[str] = Field(None, description="Suggested instruments")
    bpm: Optional[int] = Field(None, description="Suggested tempo in BPM")
    hook_line: Optional[str] = Field(None, description="Catchy hook line")
    tags: List[str] = Field(default_factory=list, description="Short tags for the song")


class Lyricist(BaseAgent):
    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def generate_lyrics(
        self,
        idea: str,
        user_requirement: str,
        style: str,
        audience: Optional[str] = None,
        trendy: bool = False,
    ) -> LyricsDraft:
        parser = PydanticOutputParser(pydantic_object=LyricsDraft)
        messages = [
            SystemMessage(
                content=system_prompt_template.format(
                    format_instructions=parser.get_format_instructions()
                )
            ),
            HumanMessage(
                content=human_prompt_template.format(
                    idea=idea,
                    user_requirement=user_requirement,
                    style=style,
                    audience=audience or "",
                    trendy="true" if trendy else "false",
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, LyricsDraft)
