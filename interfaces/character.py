from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Union, Dict
from PIL import Image




class CharacterInScene(BaseModel):
    idx: int = Field(
        description="The index of the character in the scene, starting from 0",
    )
    identifier_in_scene: str = Field(
        description="The identifier for the character in this specific scene, which may differ from the base identifier",
        examples=["Alice", "Bob the Builder"],
    )
    is_visible: bool = Field(
        description="Indicates whether the character is visible in this scene",
        examples=[True, False],
    )
    static_features: str = Field(
        default="",
        description="The static features of the character in this specific scene, such as facial features and body shape that remain constant or are rarely changed. If the character is not visible, this field can be left empty.",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build.",
            "Bob the Builder is a middle-aged man with a sturdy build.",
        ]
    )
    dynamic_features: str = Field(
        default="",
        description="The dynamic features of the character in this specific scene, such as clothing and accessories that may change from scene to scene. If not mentioned, this field can be left empty. If the character is not visible, this field should be None.",
        examples=[
            "Wearing a red scarf and a black leather jacket",
        ]
    )
    
    @field_validator("static_features", "dynamic_features", mode="before")
    @classmethod
    def coerce_none_to_empty_string(cls, v):
        """Coerce None to empty string for features fields."""
        return v if v is not None else ""
    # Rich character profile fields (optional, populated from S3)
    description: Optional[str] = Field(
        default=None,
        description="A general description of the character's background and role in the story.",
    )
    personality: Optional[str] = Field(
        default=None,
        description="The character's personality traits and behavioral characteristics.",
    )
    voice_description: Optional[str] = Field(
        default=None,
        description="Description of the character's voice, tone, and speaking style.",
    )
    role: Optional[str] = Field(
        default=None,
        description="The character's role in the narrative (e.g., main_host, co_host, storyteller, guide, expert).",
    )
    traits: Optional[List[str]] = Field(
        default=None,
        description="A list of character traits for quick reference.",
    )
    appearance: Optional[str] = Field(
        default=None,
        description="Detailed appearance description separate from static_features.",
    )

    def __str__(self):
        # Alice[visible]
        # static features: Alice has long blonde hair and blue eyes, and is of slender build.
        # dynamic features: Wearing a red scarf and a black leather jacket

        s = f"{self.identifier_in_scene}"
        s += "[visible]" if self.is_visible else "[not visible]"
        if self.role:
            s += f" (role: {self.role})"
        s += "\n"
        if self.description:
            s += f"description: {self.description}\n"
        if self.personality:
            s += f"personality: {self.personality}\n"
        if self.voice_description:
            s += f"voice: {self.voice_description}\n"
        if self.traits:
            s += f"traits: {', '.join(self.traits)}\n"
        if self.appearance:
            s += f"appearance: {self.appearance}\n"
        s += f"static features: {self.static_features}\n"
        s += f"dynamic features: {self.dynamic_features}\n"

        return s
    
    def to_profile_context(self) -> str:
        """Generate a rich profile context string for agent prompts."""
        lines = [f"{self.identifier_in_scene}:"]
        if self.description:
            lines.append(f"  Description: {self.description}")
        if self.personality:
            lines.append(f"  Personality: {self.personality}")
        if self.voice_description:
            lines.append(f"  Voice: {self.voice_description}")
        if self.role:
            lines.append(f"  Role: {self.role}")
        if self.traits:
            lines.append(f"  Traits: {', '.join(self.traits)}")
        if self.appearance:
            lines.append(f"  Appearance: {self.appearance}")
        lines.append(f"  Visual Features: {self.static_features}")
        return "\n".join(lines)



class CharacterInEvent(BaseModel):
    index: int = Field(
        description="The index of the character in the event, starting from 0",
    )
    identifier_in_event: str = Field(
        description="The unique identifier for the character in the event",
        examples=["Alice", "Bob the Builder"],
    )

    active_scenes: Dict[int, str] = Field(
        description="A dictionary mapping scene indices to their identifiers in specific scenes.",
        examples=[
            {0: "Alice", 2: "Alice in Wonderland", 5: "Alice"},
            {1: "Bob the Builder", 3: "Bob", 4: "Bob"},
        ]
    )

    static_features: str = Field(
        description="The static features of the character in the event, such as facial features and body shape that remain constant or are rarely changed.",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build. She often wears casual, comfortable clothing.",
            "Bob the Builder is a middle-aged man with a sturdy build. He typically wears a hard hat and work overalls.",
        ]
    )



class CharacterInNovel(BaseModel):
    index: int = Field(
        description="The index of the character in the novel, starting from 0",
    )
    identifier_in_novel: str = Field(
        description="The unique identifier for the character in the novel",
        examples=["Alice", "Bob the Builder"],
    )

    active_events: Dict[int, str] = Field(
        description="A dictionary mapping event indices to their identifiers in specific events.",
        examples=[
            {0: "Alice", 2: "Alice in Wonderland", 5: "Alice"},
            {1: "Bob the Builder", 3: "Bob", 4: "Bob"},
        ]
    )

    static_features: str = Field(
        description="The static features of the character in the novel, such as facial features and body shape that remain constant or are rarely changed.",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build. She often wears casual, comfortable clothing.",
            "Bob the Builder is a middle-aged man with a sturdy build. He typically wears a hard hat and work overalls.",
        ]
    )

