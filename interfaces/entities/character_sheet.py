"""Character sheet data models for unified character representation.

A character sheet is a single 3x3 grid image containing all views and expressions
of a character, enabling consistent character representation across video pipelines.

Grid layout:
+------------+------------+------------+
|  front     |   side     |   back     |  <- Neutral
|  neutral   |   neutral  |   neutral  |
+------------+------------+------------+
|  front     |   side     |   back     |  <- Happy
|  happy     |   happy    |   happy    |
+------------+------------+------------+
|  front     |   side     |   back     |  <- Sad
|  sad       |   sad      |   sad      |
+------------+------------+------------+
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, Optional


class CharacterView(str, Enum):
    """Camera angle/view of the character."""
    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class CharacterExpression(str, Enum):
    """Facial expression of the character."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"


# Grid constants
SHEET_COLUMNS = [CharacterView.FRONT, CharacterView.SIDE, CharacterView.BACK]
SHEET_ROWS = [CharacterExpression.NEUTRAL, CharacterExpression.HAPPY, CharacterExpression.SAD]
CELL_SIZE = 512  # pixels
SHEET_WIDTH = CELL_SIZE * len(SHEET_COLUMNS)  # 1536 pixels
SHEET_HEIGHT = CELL_SIZE * len(SHEET_ROWS)  # 1536 pixels


class CharacterViewData(BaseModel):
    """Data for a single character view (one cell from the sheet)."""
    path: str = Field(
        description="File path or URL to the extracted view image"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of this view"
    )


class CharacterViewSet(BaseModel):
    """All expression variants for a single view (front/side/back)."""
    neutral: Optional[CharacterViewData] = Field(
        default=None,
        description="Neutral expression variant"
    )
    happy: Optional[CharacterViewData] = Field(
        default=None,
        description="Happy expression variant"
    )
    sad: Optional[CharacterViewData] = Field(
        default=None,
        description="Sad expression variant"
    )
    
    def get_expression(self, expression: CharacterExpression) -> Optional[CharacterViewData]:
        """Get view data for a specific expression."""
        return getattr(self, expression.value, None)
    
    def get_default(self) -> Optional[CharacterViewData]:
        """Get the default (neutral) expression, or first available."""
        return self.neutral or self.happy or self.sad


class CharacterSheet(BaseModel):
    """Complete character sheet with all views and expressions.
    
    Contains the full grid image path plus extracted individual views.
    This is the new standard format for character portrait registries.
    """
    character_id: str = Field(
        description="Unique identifier for the character"
    )
    
    sheet: Optional[CharacterViewData] = Field(
        default=None,
        description="The full 3x3 character sheet grid image"
    )
    
    front: Optional[CharacterViewSet] = Field(
        default=None,
        description="Front view variants (all expressions)"
    )
    
    side: Optional[CharacterViewSet] = Field(
        default=None,
        description="Side view variants (all expressions)"
    )
    
    back: Optional[CharacterViewSet] = Field(
        default=None,
        description="Back view variants (all expressions)"
    )
    
    def get_view(
        self,
        view: CharacterView,
        expression: CharacterExpression = CharacterExpression.NEUTRAL
    ) -> Optional[CharacterViewData]:
        """Get a specific view+expression combination.
        
        Args:
            view: The camera view (front/side/back)
            expression: The facial expression (neutral/happy/sad)
            
        Returns:
            CharacterViewData if available, None otherwise
        """
        view_set = getattr(self, view.value, None)
        if view_set is None:
            return None
        return view_set.get_expression(expression)
    
    def get_view_path(
        self,
        view: CharacterView,
        expression: CharacterExpression = CharacterExpression.NEUTRAL
    ) -> Optional[str]:
        """Get the file path for a specific view+expression.
        
        Falls back to neutral expression if requested expression not available.
        Falls back to front view if requested view not available.
        """
        # Try requested view+expression
        view_data = self.get_view(view, expression)
        if view_data:
            return view_data.path
        
        # Fall back to neutral expression for requested view
        if expression != CharacterExpression.NEUTRAL:
            view_data = self.get_view(view, CharacterExpression.NEUTRAL)
            if view_data:
                return view_data.path
        
        # Fall back to front view with requested expression
        if view != CharacterView.FRONT:
            view_data = self.get_view(CharacterView.FRONT, expression)
            if view_data:
                return view_data.path
        
        # Final fallback to front neutral
        view_data = self.get_view(CharacterView.FRONT, CharacterExpression.NEUTRAL)
        if view_data:
            return view_data.path
        
        return None
    
    def to_legacy_registry_format(self) -> Dict:
        """Convert to legacy registry format for backwards compatibility.
        
        Legacy format:
        {
            "front": {"path": "...", "description": "..."},
            "side": {"path": "...", "description": "..."},
            "back": {"path": "...", "description": "..."}
        }
        """
        result = {}
        
        for view in CharacterView:
            view_data = self.get_view(view, CharacterExpression.NEUTRAL)
            if view_data:
                result[view.value] = {
                    "path": view_data.path,
                    "description": view_data.description
                }
        
        return result
    
    @classmethod
    def from_legacy_registry(cls, character_id: str, legacy_data: Dict) -> "CharacterSheet":
        """Create CharacterSheet from legacy registry format.
        
        Legacy format:
        {
            "front": {"path": "...", "description": "..."},
            "side": {"path": "...", "description": "..."},
            "back": {"path": "...", "description": "..."}
        }
        """
        sheet = cls(character_id=character_id)
        
        for view in CharacterView:
            view_entry = legacy_data.get(view.value)
            if view_entry:
                # Handle both dict and string path formats
                if isinstance(view_entry, dict):
                    path = view_entry.get("path", "")
                    description = view_entry.get("description")
                else:
                    path = str(view_entry)
                    description = None
                
                if path:
                    view_data = CharacterViewData(path=path, description=description)
                    view_set = CharacterViewSet(neutral=view_data)
                    setattr(sheet, view.value, view_set)
        
        return sheet
    
    def to_full_registry_format(self) -> Dict:
        """Convert to full registry format with all views and expressions.
        
        New format:
        {
            "sheet": {"path": "...", "description": "..."},
            "front": {
                "neutral": {"path": "...", "description": "..."},
                "happy": {"path": "...", "description": "..."},
                "sad": {"path": "...", "description": "..."}
            },
            ...
        }
        """
        result = {}
        
        if self.sheet:
            result["sheet"] = {
                "path": self.sheet.path,
                "description": self.sheet.description
            }
        
        for view in CharacterView:
            view_set = getattr(self, view.value, None)
            if view_set:
                view_dict = {}
                for expression in CharacterExpression:
                    expr_data = view_set.get_expression(expression)
                    if expr_data:
                        view_dict[expression.value] = {
                            "path": expr_data.path,
                            "description": expr_data.description
                        }
                if view_dict:
                    result[view.value] = view_dict
        
        return result


class CharacterSheetRegistry(BaseModel):
    """Registry of all character sheets for a pipeline run."""
    characters: Dict[str, CharacterSheet] = Field(
        default_factory=dict,
        description="Map of character_id to CharacterSheet"
    )
    
    def get_portrait_path(
        self,
        character_id: str,
        view: CharacterView = CharacterView.FRONT,
        expression: CharacterExpression = CharacterExpression.NEUTRAL
    ) -> Optional[str]:
        """Get portrait path for a character with specific view and expression."""
        sheet = self.characters.get(character_id)
        if sheet:
            return sheet.get_view_path(view, expression)
        return None
    
    def add_character(self, sheet: CharacterSheet):
        """Add a character sheet to the registry."""
        self.characters[sheet.character_id] = sheet
    
    def to_legacy_format(self) -> Dict[str, Dict]:
        """Convert entire registry to legacy format."""
        return {
            char_id: sheet.to_legacy_registry_format()
            for char_id, sheet in self.characters.items()
        }
    
    def to_full_format(self) -> Dict[str, Dict]:
        """Convert entire registry to full format with all views/expressions."""
        return {
            char_id: sheet.to_full_registry_format()
            for char_id, sheet in self.characters.items()
        }
    
    @classmethod
    def from_legacy_registry(cls, legacy_registry: Dict[str, Dict]) -> "CharacterSheetRegistry":
        """Create registry from legacy format."""
        registry = cls()
        for char_id, char_data in legacy_registry.items():
            sheet = CharacterSheet.from_legacy_registry(char_id, char_data)
            registry.add_character(sheet)
        return registry
