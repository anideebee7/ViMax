"""Continuity memory system for tracking state across video shots.

This module provides classes and utilities for maintaining visual continuity
across shots and scenes in video pipelines. It tracks:
- Character states (positions, expressions, clothing)
- Prop states (locations, states)
- Background/establishment frames per scene
- Previous shot references for smooth transitions
"""

import logging
import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from interfaces.entities.character_sheet import (
    CharacterView,
    CharacterExpression,
    CharacterSheet,
    CharacterSheetRegistry,
)
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)


logger = logging.getLogger(__name__)


class Position(str, Enum):
    """Character/prop position in frame."""
    LEFT = "left"
    CENTER_LEFT = "center-left"
    CENTER = "center"
    CENTER_RIGHT = "center-right"
    RIGHT = "right"
    BACKGROUND = "background"
    FOREGROUND = "foreground"


@dataclass
class CharacterState:
    """Tracks the state of a character across shots."""
    character_id: str
    position: Position = Position.CENTER
    view: CharacterView = CharacterView.FRONT
    expression: CharacterExpression = CharacterExpression.NEUTRAL
    scale: float = 0.4
    clothing: Optional[str] = None
    holding: Optional[str] = None  # Prop ID if holding something
    last_shot_idx: int = -1
    last_frame_path: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "character_id": self.character_id,
            "position": self.position.value,
            "view": self.view.value,
            "expression": self.expression.value,
            "scale": self.scale,
            "clothing": self.clothing,
            "holding": self.holding,
            "last_shot_idx": self.last_shot_idx,
            "last_frame_path": self.last_frame_path,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CharacterState":
        """Create from dictionary."""
        return cls(
            character_id=data["character_id"],
            position=Position(data.get("position", "center")),
            view=CharacterView(data.get("view", "front")),
            expression=CharacterExpression(data.get("expression", "neutral")),
            scale=data.get("scale", 0.4),
            clothing=data.get("clothing"),
            holding=data.get("holding"),
            last_shot_idx=data.get("last_shot_idx", -1),
            last_frame_path=data.get("last_frame_path"),
        )


@dataclass
class PropState:
    """Tracks the state of a prop across shots."""
    prop_id: str
    location: str = ""  # e.g., "CharacterA's hand", "on table", "background"
    state: str = "normal"  # e.g., "normal", "glowing", "broken"
    position: Position = Position.CENTER
    visible: bool = True
    held_by: Optional[str] = None  # Character ID if being held
    last_shot_idx: int = -1
    last_frame_path: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "prop_id": self.prop_id,
            "location": self.location,
            "state": self.state,
            "position": self.position.value,
            "visible": self.visible,
            "held_by": self.held_by,
            "last_shot_idx": self.last_shot_idx,
            "last_frame_path": self.last_frame_path,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PropState":
        """Create from dictionary."""
        return cls(
            prop_id=data["prop_id"],
            location=data.get("location", ""),
            state=data.get("state", "normal"),
            position=Position(data.get("position", "center")),
            visible=data.get("visible", True),
            held_by=data.get("held_by"),
            last_shot_idx=data.get("last_shot_idx", -1),
            last_frame_path=data.get("last_frame_path"),
        )


@dataclass
class SceneContext:
    """Context for a scene including establishment frames."""
    scene_id: str
    location: Optional[str] = None
    establishment_frame_path: Optional[str] = None
    lighting: Optional[str] = None
    mood: Optional[str] = None
    time_of_day: Optional[str] = None
    last_shot_idx: int = -1
    shot_count: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "scene_id": self.scene_id,
            "location": self.location,
            "establishment_frame_path": self.establishment_frame_path,
            "lighting": self.lighting,
            "mood": self.mood,
            "time_of_day": self.time_of_day,
            "last_shot_idx": self.last_shot_idx,
            "shot_count": self.shot_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SceneContext":
        """Create from dictionary."""
        return cls(
            scene_id=data["scene_id"],
            location=data.get("location"),
            establishment_frame_path=data.get("establishment_frame_path"),
            lighting=data.get("lighting"),
            mood=data.get("mood"),
            time_of_day=data.get("time_of_day"),
            last_shot_idx=data.get("last_shot_idx", -1),
            shot_count=data.get("shot_count", 0),
        )


class ContinuityMemory:
    """Tracks continuity state across shots and scenes.
    
    This class maintains memory of:
    - Character states (positions, views, expressions, what they're holding)
    - Prop states (locations, states, visibility)
    - Scene establishments (first frame of each scene for background consistency)
    - Previous shot frames (for smooth transitions)
    - Location-based frame tracking (same location = same background)
    """
    
    def __init__(self, working_dir: Optional[str] = None):
        """Initialize continuity memory.
        
        Args:
            working_dir: Optional directory for persistence
        """
        self.character_states: Dict[str, CharacterState] = {}
        self.prop_states: Dict[str, PropState] = {}
        self.scene_contexts: Dict[str, SceneContext] = {}
        self.location_establishment_frames: Dict[str, str] = {}
        self.previous_shot_frame: Optional[str] = None
        self.current_shot_idx: int = 0
        self.current_scene_id: Optional[str] = None
        self.working_dir = working_dir
        
        # Character portrait registry reference
        self.portrait_registry: Optional[CharacterSheetRegistry] = None
    
    def set_portrait_registry(self, registry: CharacterSheetRegistry):
        """Set the character portrait registry for view selection."""
        self.portrait_registry = registry
    
    def get_character_state(self, character_id: str) -> CharacterState:
        """Get or create state for a character."""
        if character_id not in self.character_states:
            self.character_states[character_id] = CharacterState(character_id=character_id)
        return self.character_states[character_id]
    
    def get_prop_state(self, prop_id: str) -> PropState:
        """Get or create state for a prop."""
        if prop_id not in self.prop_states:
            self.prop_states[prop_id] = PropState(prop_id=prop_id)
        return self.prop_states[prop_id]
    
    def get_scene_context(self, scene_id: str) -> SceneContext:
        """Get or create context for a scene."""
        if scene_id not in self.scene_contexts:
            self.scene_contexts[scene_id] = SceneContext(scene_id=scene_id)
        return self.scene_contexts[scene_id]
    
    def start_scene(
        self,
        scene_id: str,
        location: Optional[str] = None,
        mood: Optional[str] = None,
        lighting: Optional[str] = None,
    ):
        """Start a new scene, initializing context."""
        self.current_scene_id = scene_id
        context = self.get_scene_context(scene_id)
        context.location = location
        context.mood = mood
        context.lighting = lighting
        logger.debug(f"Started scene {scene_id} at location: {location}")
    
    def get_reference_frames_for_shot(
        self,
        scene_id: Optional[str] = None,
        location: Optional[str] = None,
        max_refs: int = 2,
    ) -> List[str]:
        """Get reference frames for generating a new shot.
        
        Returns establishment frame and/or previous shot frame for continuity.
        
        Args:
            scene_id: Current scene ID
            location: Current location (for location-based tracking)
            max_refs: Maximum number of reference frames to return
            
        Returns:
            List of frame paths to use as references
        """
        refs = []
        
        scene_id = scene_id or self.current_scene_id
        
        # Priority 1: Scene establishment frame
        if scene_id:
            context = self.scene_contexts.get(scene_id)
            if context and context.establishment_frame_path:
                refs.append(context.establishment_frame_path)
        
        # Priority 2: Location-based establishment frame (for same locations across scenes)
        if location and location in self.location_establishment_frames:
            loc_frame = self.location_establishment_frames[location]
            if loc_frame not in refs:
                refs.append(loc_frame)
        
        # Priority 3: Previous shot frame (for smooth transitions)
        if self.previous_shot_frame and self.previous_shot_frame not in refs:
            refs.append(self.previous_shot_frame)
        
        return refs[:max_refs]
    
    def update_for_shot(
        self,
        shot_idx: int,
        frame_path: str,
        scene_id: Optional[str] = None,
        location: Optional[str] = None,
        visible_characters: Optional[List[str]] = None,
        visible_props: Optional[List[str]] = None,
        shot_description: Optional[str] = None,
    ):
        """Update continuity state after generating a shot.
        
        Args:
            shot_idx: Index of the shot
            frame_path: Path to the generated frame
            scene_id: Scene ID
            location: Location name
            visible_characters: List of visible character IDs
            visible_props: List of visible prop IDs
            shot_description: Description of the shot (for state inference)
        """
        self.current_shot_idx = shot_idx
        scene_id = scene_id or self.current_scene_id
        
        # Update scene context
        if scene_id:
            context = self.get_scene_context(scene_id)
            context.shot_count += 1
            context.last_shot_idx = shot_idx
            
            # First shot of scene becomes establishment frame
            if context.establishment_frame_path is None:
                context.establishment_frame_path = frame_path
                logger.debug(f"Set establishment frame for scene {scene_id}: {frame_path}")
        
        # Update location-based tracking
        if location and location not in self.location_establishment_frames:
            self.location_establishment_frames[location] = frame_path
            logger.debug(f"Set establishment frame for location '{location}': {frame_path}")
        
        # Update character states
        if visible_characters:
            for char_id in visible_characters:
                state = self.get_character_state(char_id)
                state.last_shot_idx = shot_idx
                state.last_frame_path = frame_path
                
                # Infer view and expression from shot description
                if shot_description:
                    state.view = get_character_view_for_shot(shot_description)
                    state.expression = get_character_expression_for_shot(shot_description)
        
        # Update prop states with position and ownership tracking
        if visible_props:
            for prop_id in visible_props:
                state = self.get_prop_state(prop_id)
                state.last_shot_idx = shot_idx
                state.last_frame_path = frame_path
                state.visible = True
                
                # Infer prop position and ownership from shot description
                if shot_description:
                    # Check if prop is held by a character
                    for char_id in (visible_characters or []):
                        if char_id.lower() in shot_description.lower() and prop_id.lower() in shot_description.lower():
                            # Check if character is holding the prop
                            char_context = shot_description.lower()
                            if any(word in char_context for word in ["holding", "carrying", "with", "has", "using"]):
                                state.held_by = char_id
                                # Update character state to reflect holding
                                char_state = self.get_character_state(char_id)
                                char_state.holding = prop_id
                            break
        
        # Infer and track lighting from shot description
        if shot_description and scene_id:
            context = self.get_scene_context(scene_id)
            lighting = self._infer_lighting_from_description(shot_description)
            if lighting:
                context.lighting = lighting
                context.time_of_day = self._infer_time_of_day_from_description(shot_description)
        
        # Update previous shot frame
        self.previous_shot_frame = frame_path
    
    def _infer_lighting_from_description(self, description: str) -> Optional[str]:
        """Infer lighting conditions from shot description."""
        desc_lower = description.lower()
        
        # Time-based lighting
        if any(word in desc_lower for word in ["dawn", "sunrise", "early morning", "morning light"]):
            return "soft warm morning light"
        elif any(word in desc_lower for word in ["noon", "midday", "bright sun", "sunny"]):
            return "bright daylight"
        elif any(word in desc_lower for word in ["sunset", "dusk", "golden hour", "evening"]):
            return "warm golden hour light"
        elif any(word in desc_lower for word in ["night", "dark", "moonlight", "nocturnal"]):
            return "dim moonlight or artificial light"
        elif any(word in desc_lower for word in ["indoor", "room", "studio", "artificial"]):
            return "indoor artificial lighting"
        
        # Mood-based lighting
        if any(word in desc_lower for word in ["dramatic", "harsh", "contrast"]):
            return "dramatic high contrast lighting"
        elif any(word in desc_lower for word in ["soft", "gentle", "diffused"]):
            return "soft diffused lighting"
        elif any(word in desc_lower for word in ["warm", "cozy", "intimate"]):
            return "warm intimate lighting"
        elif any(word in desc_lower for word in ["cool", "cold", "blue"]):
            return "cool blue lighting"
        
        return None
    
    def _infer_time_of_day_from_description(self, description: str) -> Optional[str]:
        """Infer time of day from shot description."""
        desc_lower = description.lower()
        
        if any(word in desc_lower for word in ["dawn", "sunrise", "early morning"]):
            return "dawn"
        elif any(word in desc_lower for word in ["morning", "mid-morning"]):
            return "morning"
        elif any(word in desc_lower for word in ["noon", "midday", "afternoon"]):
            return "afternoon"
        elif any(word in desc_lower for word in ["sunset", "dusk", "evening"]):
            return "evening"
        elif any(word in desc_lower for word in ["night", "midnight", "late night"]):
            return "night"
        
        return None
    
    def get_lighting_for_location(self, location: str) -> Optional[str]:
        """Get lighting condition for a location from scene context."""
        for scene_id, context in self.scene_contexts.items():
            if context.location == location and context.lighting:
                return context.lighting
        return None
    
    def get_character_portrait_path(
        self,
        character_id: str,
        shot_description: str,
        registry: Optional[Dict[str, Dict]] = None,
    ) -> Optional[str]:
        """Get the appropriate portrait path for a character based on shot context.
        
        Args:
            character_id: Character ID
            shot_description: Shot description for view/expression inference
            registry: Optional legacy portrait registry (if portrait_registry not set)
            
        Returns:
            Path to the appropriate portrait image
        """
        # Get view and expression from shot description
        view = get_character_view_for_shot(shot_description)
        expression = get_character_expression_for_shot(shot_description)
        
        # Update character state
        state = self.get_character_state(character_id)
        state.view = view
        state.expression = expression
        
        # Try new registry first
        if self.portrait_registry:
            path = self.portrait_registry.get_portrait_path(character_id, view, expression)
            if path:
                return path
        
        # Fall back to legacy registry format
        if registry and character_id in registry:
            char_data = registry[character_id]
            
            # Try new format with expressions
            view_data = char_data.get(view.value, {})
            if isinstance(view_data, dict):
                # Check for expression-specific path
                expr_data = view_data.get(expression.value, view_data.get("neutral", view_data))
                if isinstance(expr_data, dict):
                    return expr_data.get("path")
                elif isinstance(expr_data, str):
                    return expr_data
                # Fall back to view path
                return view_data.get("path")
            
            # Try legacy format (no expressions)
            front_data = char_data.get("front", {})
            if isinstance(front_data, dict):
                return front_data.get("path")
            return str(front_data) if front_data else None
        
        return None
    
    def get_props_for_shot(
        self,
        shot_description: str,
        previous_props: Optional[List[str]] = None,
    ) -> List[str]:
        """Determine which props should appear in a shot.
        
        Considers:
        - Props visible in previous shot that should persist
        - Props explicitly mentioned in shot description
        - Prop state (broken, destroyed props shouldn't appear)
        
        Args:
            shot_description: Description of the shot
            previous_props: Props visible in previous shot
            
        Returns:
            List of prop IDs that should appear
        """
        visible_props = []
        
        # Props from previous shot should persist unless explicitly removed
        if previous_props:
            for prop_id in previous_props:
                state = self.prop_states.get(prop_id)
                if state and state.visible:
                    visible_props.append(prop_id)
        
        # Check for props mentioned in description
        description_lower = shot_description.lower()
        for prop_id, state in self.prop_states.items():
            if prop_id.lower() in description_lower and state.visible:
                if prop_id not in visible_props:
                    visible_props.append(prop_id)
        
        return visible_props
    
    def get_character_layout(
        self,
        visible_characters: List[str],
        shot_description: str,
    ) -> List[Dict[str, Any]]:
        """Determine spatial layout for multiple characters in a shot.
        
        Args:
            visible_characters: List of visible character IDs
            shot_description: Shot description for position inference
            
        Returns:
            List of character layouts with position, scale, view
        """
        layout = []
        num_chars = len(visible_characters)
        
        # Default positions based on character count
        if num_chars == 1:
            default_positions = [Position.CENTER]
        elif num_chars == 2:
            default_positions = [Position.CENTER_LEFT, Position.CENTER_RIGHT]
        elif num_chars == 3:
            default_positions = [Position.LEFT, Position.CENTER, Position.RIGHT]
        else:
            # Distribute evenly
            default_positions = [
                Position.LEFT, Position.CENTER_LEFT, Position.CENTER_RIGHT, Position.RIGHT
            ][:num_chars]
        
        for i, char_id in enumerate(visible_characters):
            state = self.get_character_state(char_id)
            
            # Try to infer position from description
            position = self._infer_position_from_description(char_id, shot_description)
            if not position:
                # Use previous position if available
                if state.last_shot_idx >= 0:
                    position = state.position
                else:
                    position = default_positions[i] if i < len(default_positions) else Position.CENTER
            
            # Infer view and expression
            view = get_character_view_for_shot(shot_description)
            expression = get_character_expression_for_shot(shot_description)
            
            # Update state
            state.position = position
            state.view = view
            state.expression = expression
            
            layout.append({
                "character_id": char_id,
                "position": position.value,
                "view": view.value,
                "expression": expression.value,
                "scale": state.scale,
            })
        
        return layout
    
    def _infer_position_from_description(
        self,
        character_id: str,
        description: str,
    ) -> Optional[Position]:
        """Infer character position from shot description."""
        description_lower = description.lower()
        char_lower = character_id.lower()
        
        # Check for position keywords near character name
        if f"{char_lower}" in description_lower:
            # Find context around character mention
            idx = description_lower.find(char_lower)
            context = description_lower[max(0, idx-30):idx+len(char_lower)+30]
            
            if any(kw in context for kw in ["on the left", "left side", "to the left"]):
                return Position.LEFT
            elif any(kw in context for kw in ["on the right", "right side", "to the right"]):
                return Position.RIGHT
            elif any(kw in context for kw in ["in the center", "centered", "middle"]):
                return Position.CENTER
            elif any(kw in context for kw in ["background", "behind", "in the back"]):
                return Position.BACKGROUND
            elif any(kw in context for kw in ["foreground", "in front", "close up"]):
                return Position.FOREGROUND
        
        return None
    
    def save(self, path: Optional[str] = None):
        """Save continuity state to JSON file."""
        if path is None:
            if self.working_dir:
                path = os.path.join(self.working_dir, "continuity_state.json")
            else:
                logger.warning("No path provided and no working_dir set, cannot save")
                return
        
        state = {
            "character_states": {
                k: v.to_dict() for k, v in self.character_states.items()
            },
            "prop_states": {
                k: v.to_dict() for k, v in self.prop_states.items()
            },
            "scene_contexts": {
                k: v.to_dict() for k, v in self.scene_contexts.items()
            },
            "location_establishment_frames": self.location_establishment_frames,
            "previous_shot_frame": self.previous_shot_frame,
            "current_shot_idx": self.current_shot_idx,
            "current_scene_id": self.current_scene_id,
        }
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        
        logger.debug(f"Saved continuity state to {path}")
    
    def load(self, path: Optional[str] = None):
        """Load continuity state from JSON file."""
        if path is None:
            if self.working_dir:
                path = os.path.join(self.working_dir, "continuity_state.json")
            else:
                logger.warning("No path provided and no working_dir set, cannot load")
                return
        
        if not os.path.exists(path):
            logger.debug(f"No continuity state file found at {path}")
            return
        
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        
        self.character_states = {
            k: CharacterState.from_dict(v)
            for k, v in state.get("character_states", {}).items()
        }
        self.prop_states = {
            k: PropState.from_dict(v)
            for k, v in state.get("prop_states", {}).items()
        }
        self.scene_contexts = {
            k: SceneContext.from_dict(v)
            for k, v in state.get("scene_contexts", {}).items()
        }
        self.location_establishment_frames = state.get("location_establishment_frames", {})
        self.previous_shot_frame = state.get("previous_shot_frame")
        self.current_shot_idx = state.get("current_shot_idx", 0)
        self.current_scene_id = state.get("current_scene_id")
        
        logger.debug(f"Loaded continuity state from {path}")
    
    def reset(self):
        """Reset all continuity state."""
        self.character_states.clear()
        self.prop_states.clear()
        self.scene_contexts.clear()
        self.location_establishment_frames.clear()
        self.previous_shot_frame = None
        self.current_shot_idx = 0
        self.current_scene_id = None
    
    def save_series_state(self, path: Optional[str] = None):
        """Save continuity state for cross-episode persistence in series.
        
        This preserves character states, prop states, and location establishment
        frames across episodes in a series.
        
        Args:
            path: Optional path to save state. Defaults to working_dir/series_continuity.json
        """
        if path is None:
            if self.working_dir:
                path = os.path.join(self.working_dir, "series_continuity.json")
            else:
                logger.warning("No path provided and no working_dir set, cannot save series state")
                return
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        state = {
            "character_states": {
                k: v.to_dict() for k, v in self.character_states.items()
            },
            "prop_states": {
                k: v.to_dict() for k, v in self.prop_states.items()
            },
            "location_establishment_frames": self.location_establishment_frames,
            "scene_contexts": {
                k: v.to_dict() for k, v in self.scene_contexts.items()
            },
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        
        logger.debug(f"Saved series continuity state to {path}")
    
    def load_series_state(self, path: Optional[str] = None):
        """Load continuity state for cross-episode persistence in series.
        
        This restores character states, prop states, and location establishment
        frames from previous episodes.
        
        Args:
            path: Optional path to load state from. Defaults to working_dir/series_continuity.json
        """
        if path is None:
            if self.working_dir:
                path = os.path.join(self.working_dir, "series_continuity.json")
            else:
                logger.warning("No path provided and no working_dir set, cannot load series state")
                return
        
        if not os.path.exists(path):
            logger.debug(f"No series continuity state file found at {path}")
            return
        
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        
        # Load character states (merge with existing, don't replace)
        for k, v in state.get("character_states", {}).items():
            if k not in self.character_states:
                self.character_states[k] = CharacterState.from_dict(v)
            else:
                # Merge: keep latest shot info but preserve clothing/accessories
                existing = self.character_states[k]
                loaded = CharacterState.from_dict(v)
                if loaded.clothing and not existing.clothing:
                    existing.clothing = loaded.clothing
                if loaded.holding and not existing.holding:
                    existing.holding = loaded.holding
        
        # Load prop states (merge with existing)
        for k, v in state.get("prop_states", {}).items():
            if k not in self.prop_states:
                self.prop_states[k] = PropState.from_dict(v)
        
        # Load location establishment frames (merge)
        for k, v in state.get("location_establishment_frames", {}).items():
            if k not in self.location_establishment_frames:
                self.location_establishment_frames[k] = v
        
        # Load scene contexts (merge)
        for k, v in state.get("scene_contexts", {}).items():
            if k not in self.scene_contexts:
                self.scene_contexts[k] = SceneContext.from_dict(v)
        
        logger.debug(f"Loaded series continuity state from {path}")
    
    def get_transition_reference(self) -> Optional[str]:
        """Get the best reference frame for generating a transition.
        
        Returns:
            Path to previous shot frame, or establishment frame if available
        """
        if self.previous_shot_frame and os.path.exists(self.previous_shot_frame):
            return self.previous_shot_frame
        
        # Fallback to most recent scene establishment frame
        if self.current_scene_id:
            context = self.scene_contexts.get(self.current_scene_id)
            if context and context.establishment_frame_path and os.path.exists(context.establishment_frame_path):
                return context.establishment_frame_path
        
        return None
