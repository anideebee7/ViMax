import json
import os
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from interfaces.entities.prop import PropInScene

class WorldState(BaseModel):
    locations: Dict[str, str] = Field(default_factory=dict, description="Current state of locations")
    visual_anchors: Dict[str, List[str]] = Field(default_factory=dict, description="Persistent visual anchors per location slugline")
    world_changes: List[str] = Field(default_factory=list, description="Major permanent changes to the world state (e.g., 'The capital city is destroyed')")
    location_states: Dict[str, str] = Field(default_factory=dict, description="Specific state of a location (e.g., 'burned', 'renovated')")
    timeline: List[str] = Field(default_factory=list, description="Sequence of major events")
    active_plots: List[str] = Field(default_factory=list, description="Currently unresolved plot points")
    global_rules: List[str] = Field(default_factory=list, description="Established rules of the world")

class CharacterKnowledge(BaseModel):
    identifier: str
    current_status: str = "Active"
    relationships: Dict[str, str] = Field(default_factory=dict, description="Relation to other characters")
    key_memories: List[str] = Field(default_factory=list, description="Important events this character remembers")
    internal_conflict: Optional[str] = None
    inventory: List[str] = Field(default_factory=list, description="Items currently held by character")
    voice_id: Optional[str] = None

class PropReference(BaseModel):
    identifier: str
    description: str
    static_features: str
    reference_image_path: Optional[str] = None

class SeriesBible(BaseModel):
    """Utility to maintain persistent world state and character knowledge across episodes."""
    series_title: str
    world_state: WorldState = Field(default_factory=WorldState)
    characters: Dict[str, CharacterKnowledge] = Field(default_factory=dict)
    props: Dict[str, PropReference] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def save(self, working_dir: str):
        path = os.path.join(working_dir, "series_bible.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)
        logging.info(f"Series bible saved to {path}")

    @classmethod
    def load(cls, working_dir: str, series_title: str = "Untitled Series") -> "SeriesBible":
        path = os.path.join(working_dir, "series_bible.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logging.info(f"Series bible loaded from {path}")
            return cls.model_validate(data)
        else:
            logging.info("No existing series bible found. Creating new one.")
            return cls(series_title=series_title)

    def update_character(self, character_id: str, updates: Dict[str, Any]):
        if character_id not in self.characters:
            self.characters[character_id] = CharacterKnowledge(identifier=character_id)
        
        char = self.characters[character_id]
        for key, value in updates.items():
            if hasattr(char, key):
                if isinstance(value, list) and isinstance(getattr(char, key), list):
                    getattr(char, key).extend(value)
                elif isinstance(value, dict) and isinstance(getattr(char, key), dict):
                    getattr(char, key).update(value)
                else:
                    setattr(char, key, value)

    def record_event(self, event_description: str):
        self.world_state.timeline.append(event_description)

    def register_prop(self, prop: PropInScene, reference_image_path: Optional[str] = None):
        if prop.identifier not in self.props:
            self.props[prop.identifier] = PropReference(
                identifier=prop.identifier,
                description=prop.description,
                static_features=prop.static_features,
                reference_image_path=reference_image_path
            )
        elif reference_image_path:
            self.props[prop.identifier].reference_image_path = reference_image_path

    def add_visual_anchor(self, slugline: str, anchor: str):
        if slugline not in self.world_state.visual_anchors:
            self.world_state.visual_anchors[slugline] = []
        if anchor not in self.world_state.visual_anchors[slugline]:
            self.world_state.visual_anchors[slugline].append(anchor)

    def update_location_state(self, slugline: str, state_description: str):
        self.world_state.location_states[slugline] = state_description
        self.record_event(f"Location '{slugline}' updated state: {state_description}")

    def record_world_change(self, change_description: str):
        self.world_state.world_changes.append(change_description)
        self.record_event(f"World change recorded: {change_description}")
