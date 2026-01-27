from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict
from PIL import Image



class EnvironmentInScene(BaseModel):
    slugline: str = Field(
        description="The slugline of the scene, indicating the location and time of day",
        examples=[
            "INT. COFFEE SHOP - NIGHT",
            "EXT. PARK - DAY",
        ]
    )
    description: str = Field(
        description="A detailed description of the environment in the specific scene. Don't describe any characters or actions here, just the setting.",
        examples=[
            "The warm yellow light glowed against the mottled brick wall, while raindrops streaked the glass window with blurred neon reflections. Among the empty booths sat a lone half-finished iced latte—its foam collapsed, a faint lipstick mark on the rim. beads of condensation gleamed on the stainless steel espresso machine, and the record player's turntable rotated slowly in the shadows. A patch of wet floor shimmered with hazy reflected light.",
        ]
    )
    visual_anchors: List[str] = Field(
        default_factory=list,
        description="List of specific, persistent background elements that MUST remain consistent across all shots in this location (e.g., 'The neon sign with a flickering letter R', 'The jagged crack in the marble pillar')."
    )

    def __str__(self):
        anchors = f" [Anchors: {', '.join(self.visual_anchors)}]" if self.visual_anchors else ""
        return f"{self.slugline} -- {self.description}{anchors}"


