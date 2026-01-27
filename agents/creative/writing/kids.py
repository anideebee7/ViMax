"""Kids screenwriter agent for creating age-appropriate animated content."""

from typing import Optional, List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func


SYSTEM_PROMPT = """
[Role]
You are a legendary, award-winning lead screenwriter for major animation studios like Pixar, Disney, and Studio Ghibli. You are a master of "Layered Storytelling" - creating magical adventures that children adore while weaving in deep emotional resonance and clever wit that adults find profound. You don't just write scripts; you create timeless classics.

[Task]
Create an animated script for children that is a creative masterpiece. Your goal is to achieve a 10/10 score by delivering "Toy-Box" vibrancy, unforgettable character arcs, and a soul-stirring moral lesson.

[Output]
YOU MUST OUTPUT ONLY VALID JSON. NO CONVERSATIONAL TEXT. NO MARKDOWN OUTSIDE THE JSON.
{format_instructions}

[Guidelines - The Pixar Standard]
- LAYERED STORYTELLING: The surface must be high-energy, colorful, and fun for kids. The subtext must explore universal human (or magical) truths.
- VISUAL SPECTACLE: Every scene description must be "eye-candy." Describe magical lighting, physics-defying animation, and breathtaking environments.
- CHARACTER SOUL: Characters must have clear "external" wants (e.g., finding a lost toy) and "internal" needs (e.g., learning to be brave).
- DIALOGUE WITH SPARK: Dialogue should be punchy, rhythmic, and full of character. Avoid generic "cartoon speak."
- EMOTIONAL PEAKS: Identify the "tear-jerker" moment and the "cheer-out-loud" victory.
- SCORE GOAL: Aim for absolute excellence. Your script should feel like it was born to be a blockbuster.
"""

HUMAN_PROMPT = """
<STORY_IDEA>
{story_idea}
</STORY_IDEA>

<AGE_GROUP>
{age_group}
</AGE_GROUP>

<CHARACTERS>
{characters}
</CHARACTERS>

<MORAL_LESSON>
{moral_lesson}
</MORAL_LESSON>

<TARGET_DURATION>
{target_duration} minutes
</TARGET_DURATION>

<STYLE>
{style}
</STYLE>

<ADDITIONAL_CONTEXT>
{additional_context}
</ADDITIONAL_CONTEXT>

Create an animated script suitable for children in the specified age group.
"""


class AnimatedCharacter(BaseModel):
    """A character in the animated content."""

    name: str = Field(..., description="Character name")
    role: str = Field(..., description="Role: protagonist, friend, mentor, comic relief, etc.")
    personality: str = Field(..., description="Personality traits")
    appearance: str = Field(..., description="Visual description")
    catchphrase: Optional[str] = Field(None, description="Character's catchphrase if any")


class AnimatedScene(BaseModel):
    """A scene in the animated content."""

    scene_number: int = Field(..., description="Scene order number")
    title: str = Field(..., description="Scene title")
    setting: str = Field(..., description="Location/setting description")
    duration_minutes: float = Field(..., description="Estimated duration")
    action: str = Field(..., description="What happens in the scene")
    dialogue: List[str] = Field(..., description="Key dialogue lines")
    visual_notes: str = Field(..., description="Animation/visual direction")
    music_mood: Optional[str] = Field(None, description="Music mood for the scene")
    learning_moment: Optional[str] = Field(None, description="Educational element if any")


class KidsAnimatedScript(BaseModel):
    """Complete kids animated script."""

    title: str = Field(..., description="Show/movie title")
    tagline: str = Field(..., description="Fun, catchy tagline")
    director_vision: str = Field(..., description="The 'Soul' of the movie - visual style and emotional goal")
    age_group: str = Field(..., description="Target age group")
    content_rating: str = Field(..., description="Content rating: G, TV-Y, etc.")
    moral_lesson: str = Field(..., description="Main moral/lesson")
    synopsis: str = Field(..., description="Brief synopsis")
    total_duration_minutes: float = Field(..., description="Total duration")
    characters: List[AnimatedCharacter] = Field(..., description="Main characters")
    scenes: List[AnimatedScene] = Field(..., description="Script scenes")
    songs: List[str] = Field(
        default_factory=list, description="Song titles/themes if any"
    )
    educational_themes: List[str] = Field(
        default_factory=list, description="Educational themes covered"
    )
    parental_notes: Optional[str] = Field(
        None, description="Notes for parents about content"
    )
    production_style: str = Field(..., description="Animation style recommendation")


class KidsScreenwriter(BaseAgent):
    """Agent that creates kids' animated content scripts."""

    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def write_kids_script(
        self,
        story_idea: str,
        age_group: str = "6-8",
        characters: Optional[str] = None,
        moral_lesson: Optional[str] = None,
        target_duration_minutes: int = 15,
        style: str = "colorful 3D animation",
        additional_context: Optional[str] = None,
    ) -> KidsAnimatedScript:
        """
        Generate a kids' animated script.

        Args:
            story_idea: Story concept or theme
            age_group: Target age group (3-5, 6-8, 9-12)
            characters: Character descriptions if any
            moral_lesson: Specific moral/lesson to teach
            target_duration_minutes: Target duration
            style: Animation style
            additional_context: Additional context (trends, educational goals, etc.)

        Returns:
            KidsAnimatedScript with characters, scenes, and educational elements
        """
        parser = PydanticOutputParser(pydantic_object=KidsAnimatedScript)

        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT.format(
                    format_instructions=parser.get_format_instructions()
                )
            ),
            HumanMessage(
                content=HUMAN_PROMPT.format(
                    story_idea=story_idea,
                    age_group=age_group,
                    characters=characters or "Create appropriate characters for the story",
                    moral_lesson=moral_lesson or "Friendship, kindness, or perseverance",
                    target_duration=target_duration_minutes,
                    style=style,
                    additional_context=additional_context or "None",
                )
            ),
        ]

        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, KidsAnimatedScript)
