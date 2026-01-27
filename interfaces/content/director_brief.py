"""Director brief: creative and structural guidance from Director agents to Screenwriters and Cinematographers."""

from pydantic import BaseModel, Field
from typing import List, Optional


class DirectorBrief(BaseModel):
    """
    Creative and structural brief produced by a Director agent.
    Passed to Screenwriter and Cinematographer to align tone, format, and key beats.
    """

    title: str = Field(..., description="Working title for the piece")
    format: str = Field(
        ...,
        description="Format: short_form, short_film, feature_film, documentary, kids_movie, ad, learning_series, music_video",
    )
    tone: str = Field(..., description="Overall tone and mood")
    pacing: str = Field(..., description="Pacing guidance (e.g., rapid, measured, build-and-release)")
    key_beats: List[str] = Field(
        default_factory=list,
        description="Key narrative or structural beats the director wants emphasized",
    )
    visual_style: str = Field(..., description="Visual style and look guidance")
    structure_notes: Optional[str] = Field(
        default=None,
        description="Structural notes (acts, segments, duration splits)",
    )
    additional_guidance: Optional[str] = Field(
        default=None,
        description="Any additional creative or technical guidance",
    )

    def to_context_block(self) -> str:
        """Format the brief for injection into prompts (e.g., user_requirement)."""
        lines = [
            "[Director's Creative Brief]",
            f"Title: {self.title}",
            f"Format: {self.format}",
            f"Tone: {self.tone}",
            f"Pacing: {self.pacing}",
            f"Visual style: {self.visual_style}",
        ]
        if self.key_beats:
            lines.append("Key beats: " + "; ".join(self.key_beats))
        if self.structure_notes:
            lines.append(f"Structure: {self.structure_notes}")
        if self.additional_guidance:
            lines.append(f"Additional: {self.additional_guidance}")
        return "\n".join(lines)
