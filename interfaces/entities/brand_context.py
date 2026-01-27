"""Brand and Game context interfaces for auto-ideation and content generation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class BrandVisuals(BaseModel):
    """Visual style information for a brand."""
    
    color_palette: Optional[str] = Field(
        default=None,
        description="Primary color palette for the brand"
    )
    visual_style: Optional[str] = Field(
        default=None,
        description="Overall visual style (e.g., '3D cartoon', 'minimalist', 'vibrant')"
    )
    pacing: Optional[str] = Field(
        default=None,
        description="Content pacing style (e.g., 'snappy', 'relaxed', 'energetic')"
    )
    soundtrack_style: Optional[str] = Field(
        default=None,
        description="Music/sound style for the brand"
    )


class BrandCharacterSummary(BaseModel):
    """Summary of a brand character for ideation."""
    
    name: str = Field(description="Character name")
    role: Optional[str] = Field(default=None, description="Character role (main_host, co_host, guide, etc.)")
    personality: Optional[str] = Field(default=None, description="Personality traits")
    description: Optional[str] = Field(default=None, description="Brief description")
    traits: Optional[List[str]] = Field(default=None, description="Key traits")


class BrandContext(BaseModel):
    """Complete brand context for ideation and content generation."""
    
    brand_id: str = Field(description="Brand identifier")
    name: str = Field(description="Brand name")
    description: Optional[str] = Field(default=None, description="Brand description")
    brand_story: Optional[str] = Field(default=None, description="Brand origin story or narrative")
    target_audience: Optional[str] = Field(default=None, description="Target audience")
    
    # Series information
    series_name: Optional[str] = Field(default=None, description="Series name if applicable")
    series_concept: Optional[str] = Field(default=None, description="Series concept/premise")
    
    # Visual identity
    logo_url: Optional[str] = Field(default=None, description="Brand logo URL")
    icon_url: Optional[str] = Field(default=None, description="Brand icon URL")
    visuals: Optional[BrandVisuals] = Field(default=None, description="Visual style information")
    
    # Characters
    characters: List[BrandCharacterSummary] = Field(
        default_factory=list,
        description="Available characters for the brand"
    )
    
    # Brand traits and values
    brand_traits: Optional[List[str]] = Field(
        default=None,
        description="Core brand traits/values"
    )
    content_themes: Optional[List[str]] = Field(
        default=None,
        description="Common content themes for this brand"
    )
    
    # Raw data for additional fields
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw brand.json data for additional fields"
    )
    
    def to_ideation_context(self) -> str:
        """Generate context string for ideation prompts."""
        lines = [f"<BRAND_CONTEXT>"]
        lines.append(f"Brand: {self.name}")
        
        if self.description:
            lines.append(f"Description: {self.description}")
        if self.brand_story:
            lines.append(f"Brand Story: {self.brand_story}")
        if self.target_audience:
            lines.append(f"Target Audience: {self.target_audience}")
        if self.series_name:
            lines.append(f"Series: {self.series_name}")
        if self.series_concept:
            lines.append(f"Series Concept: {self.series_concept}")
        
        if self.brand_traits:
            lines.append(f"Brand Values: {', '.join(self.brand_traits)}")
        if self.content_themes:
            lines.append(f"Content Themes: {', '.join(self.content_themes)}")
        
        if self.visuals:
            lines.append("\nVisual Style:")
            if self.visuals.visual_style:
                lines.append(f"  Style: {self.visuals.visual_style}")
            if self.visuals.color_palette:
                lines.append(f"  Colors: {self.visuals.color_palette}")
            if self.visuals.pacing:
                lines.append(f"  Pacing: {self.visuals.pacing}")
            if self.visuals.soundtrack_style:
                lines.append(f"  Sound: {self.visuals.soundtrack_style}")
        
        if self.characters:
            lines.append("\nAvailable Characters:")
            for char in self.characters[:6]:  # Limit to 6 characters
                char_line = f"  - {char.name}"
                if char.role:
                    char_line += f" ({char.role})"
                if char.personality:
                    char_line += f": {char.personality}"
                lines.append(char_line)
        
        lines.append("</BRAND_CONTEXT>")
        return "\n".join(lines)
    
    @classmethod
    def from_s3_data(
        cls,
        brand_id: str,
        brand_data: Dict[str, Any],
        characters: Optional[List[Dict[str, Any]]] = None,
        logo_url: Optional[str] = None,
        icon_url: Optional[str] = None,
    ) -> "BrandContext":
        """Create BrandContext from S3 brand.json data."""
        # Extract visuals
        look_feel = brand_data.get("look_and_feel", {})
        visuals = None
        if look_feel:
            visuals = BrandVisuals(
                color_palette=look_feel.get("colors"),
                visual_style=look_feel.get("visuals"),
                pacing=look_feel.get("pacing"),
                soundtrack_style=look_feel.get("soundtrack"),
            )
        
        # Extract character summaries
        char_summaries = []
        if characters:
            for char in characters:
                char_summaries.append(BrandCharacterSummary(
                    name=char.get("name", char.get("identifier_in_scene", "Unknown")),
                    role=char.get("role"),
                    personality=char.get("personality"),
                    description=char.get("description"),
                    traits=char.get("traits"),
                ))
        
        return cls(
            brand_id=brand_id,
            name=brand_data.get("name", brand_id),
            description=brand_data.get("description"),
            brand_story=brand_data.get("brand_story"),
            target_audience=brand_data.get("target_audience"),
            series_name=brand_data.get("series_name"),
            series_concept=brand_data.get("series_concept"),
            logo_url=logo_url,
            icon_url=icon_url,
            visuals=visuals,
            characters=char_summaries,
            brand_traits=brand_data.get("brand_traits"),
            content_themes=brand_data.get("content_themes"),
            raw_data=brand_data,
        )


class GameContext(BaseModel):
    """Complete game context for ideation and content generation."""
    
    game_id: str = Field(description="Game identifier")
    name: str = Field(description="Game name")
    description: Optional[str] = Field(default=None, description="Game description")
    genre: Optional[str] = Field(default=None, description="Game genre")
    gameplay_summary: Optional[str] = Field(default=None, description="Gameplay summary")
    target_audience: Optional[str] = Field(default=None, description="Target audience")
    
    # Visual identity
    icon_url: Optional[str] = Field(default=None, description="Game icon URL")
    
    # Game-specific
    key_features: Optional[List[str]] = Field(
        default=None,
        description="Key game features"
    )
    unique_selling_points: Optional[List[str]] = Field(
        default=None,
        description="Unique selling points"
    )
    
    # Characters
    characters: List[BrandCharacterSummary] = Field(
        default_factory=list,
        description="Available characters for the game"
    )
    
    # Content themes
    content_themes: Optional[List[str]] = Field(
        default=None,
        description="Common content themes for this game"
    )
    
    # Brand association
    brand_id: Optional[str] = Field(
        default=None,
        description="Associated brand ID"
    )
    
    # Raw data
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw game.json data"
    )
    
    def to_ideation_context(self) -> str:
        """Generate context string for ideation prompts."""
        lines = ["<GAME_CONTEXT>"]
        lines.append(f"Game: {self.name}")
        
        if self.description:
            lines.append(f"Description: {self.description}")
        if self.genre:
            lines.append(f"Genre: {self.genre}")
        if self.gameplay_summary:
            lines.append(f"Gameplay: {self.gameplay_summary}")
        if self.target_audience:
            lines.append(f"Target Audience: {self.target_audience}")
        
        if self.key_features:
            lines.append(f"Key Features: {', '.join(self.key_features)}")
        if self.unique_selling_points:
            lines.append(f"USPs: {', '.join(self.unique_selling_points)}")
        if self.content_themes:
            lines.append(f"Content Themes: {', '.join(self.content_themes)}")
        
        if self.characters:
            lines.append("\nGame Characters:")
            for char in self.characters[:6]:
                char_line = f"  - {char.name}"
                if char.role:
                    char_line += f" ({char.role})"
                if char.personality:
                    char_line += f": {char.personality}"
                lines.append(char_line)
        
        lines.append("</GAME_CONTEXT>")
        return "\n".join(lines)
    
    @classmethod
    def from_s3_data(
        cls,
        game_id: str,
        game_data: Dict[str, Any],
        characters: Optional[List[Dict[str, Any]]] = None,
        icon_url: Optional[str] = None,
    ) -> "GameContext":
        """Create GameContext from S3 game.json data."""
        # Extract character summaries
        char_summaries = []
        if characters:
            for char in characters:
                char_summaries.append(BrandCharacterSummary(
                    name=char.get("name", char.get("identifier_in_scene", "Unknown")),
                    role=char.get("role"),
                    personality=char.get("personality"),
                    description=char.get("description"),
                    traits=char.get("traits"),
                ))
        
        return cls(
            game_id=game_id,
            name=game_data.get("name", game_id),
            description=game_data.get("description"),
            genre=game_data.get("genre"),
            gameplay_summary=game_data.get("gameplay_summary"),
            target_audience=game_data.get("target_audience"),
            icon_url=icon_url,
            key_features=game_data.get("key_features"),
            unique_selling_points=game_data.get("unique_selling_points"),
            characters=char_summaries,
            content_themes=game_data.get("content_themes"),
            brand_id=game_data.get("brand"),
            raw_data=game_data,
        )
