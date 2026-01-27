from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Literal

class PropInScene(BaseModel):
    """A key object/prop in a scene that needs visual consistency."""
    identifier: str = Field(..., description="Unique name of the prop (e.g., 'Golden Amulet', 'High-Tech Tablet')")
    description: str = Field(..., description="Detailed visual description of the prop")
    static_features: str = Field(..., description="Features that never change (material, base color, engravings)")
    dynamic_features: Optional[str] = Field(None, description="Features that might change (e.g., 'glowing blue', 'cracked screen')")
    importance: Literal["critical", "high", "medium", "low"] = Field("medium")
    
    def __str__(self):
        return f"{self.identifier}: {self.description} (Static: {self.static_features})"

    def to_context_block(self) -> str:
        return f"PROP: {self.identifier}\n- Description: {self.description}\n- Details: {self.static_features}"
