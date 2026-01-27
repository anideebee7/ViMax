"""View and expression selection utilities for character portraits.

This module provides functions to intelligently select the appropriate
character view (front/side/back) and expression (neutral/happy/sad) based
on shot descriptions, camera angles, and script context.
"""

import re
import logging
from typing import Optional, Tuple, Dict, List

from interfaces.entities.character_sheet import (
    CharacterView,
    CharacterExpression,
    CharacterSheet,
    CharacterSheetRegistry,
)


logger = logging.getLogger(__name__)


# Keywords that indicate specific camera angles/views
BACK_VIEW_KEYWORDS = [
    "from behind",
    "back view",
    "walking away",
    "facing away",
    "their back",
    "his back",
    "her back",
    "turned away",
    "back to camera",
    "back to the camera",
    "back toward",
    "looking away from camera",
    "rear view",
    "from the back",
    "following behind",
    "watched from behind",
]

SIDE_VIEW_KEYWORDS = [
    "profile",
    "side view",
    "looking left",
    "looking right",
    "faces left",
    "faces right",
    "turned to the side",
    "from the side",
    "sideways",
    "lateral view",
    "profile shot",
    "side angle",
    "in profile",
    "90 degree",
    "three-quarter",
    "3/4 view",
]

FRONT_VIEW_KEYWORDS = [
    "front view",
    "facing camera",
    "facing the camera",
    "looking at camera",
    "looking directly",
    "straight ahead",
    "toward camera",
    "head on",
    "facing forward",
    "facing us",
    "looking at us",
    "eye contact",
]

# Keywords that indicate specific emotions/expressions
HAPPY_EXPRESSION_KEYWORDS = [
    "happy",
    "smiling",
    "smile",
    "laughing",
    "joyful",
    "excited",
    "delighted",
    "cheerful",
    "grinning",
    "beaming",
    "elated",
    "pleased",
    "thrilled",
    "overjoyed",
    "gleeful",
    "content",
    "satisfied",
    "amused",
    "playful",
    "celebrating",
    "jubilant",
]

SAD_EXPRESSION_KEYWORDS = [
    "sad",
    "crying",
    "tears",
    "unhappy",
    "depressed",
    "melancholy",
    "sorrowful",
    "grieving",
    "mourning",
    "heartbroken",
    "disappointed",
    "dejected",
    "gloomy",
    "somber",
    "downcast",
    "despondent",
    "miserable",
    "weeping",
    "upset",
    "distressed",
    "anguished",
    "forlorn",
]

# Additional emotion keywords that map to neutral (as fallback)
NEUTRAL_EXPRESSION_KEYWORDS = [
    "neutral",
    "calm",
    "serious",
    "focused",
    "determined",
    "stoic",
    "expressionless",
    "composed",
    "thoughtful",
    "contemplative",
    "pensive",
    "blank",
    "impassive",
]


def get_character_view_for_shot(
    shot_description: str,
    camera_angle: Optional[str] = None,
    character_action: Optional[str] = None,
) -> CharacterView:
    """Determine which character view to use based on shot context.
    
    Args:
        shot_description: Description of the shot/scene
        camera_angle: Optional camera angle description
        character_action: Optional description of what the character is doing
        
    Returns:
        CharacterView enum (FRONT, SIDE, or BACK)
    """
    # Combine all text for analysis
    text_parts = [shot_description]
    if camera_angle:
        text_parts.append(camera_angle)
    if character_action:
        text_parts.append(character_action)
    
    combined_text = " ".join(text_parts).lower()
    
    # Check for back view indicators first (most specific)
    for keyword in BACK_VIEW_KEYWORDS:
        if keyword in combined_text:
            logger.debug(f"Selected BACK view due to keyword: '{keyword}'")
            return CharacterView.BACK
    
    # Check for side view indicators
    for keyword in SIDE_VIEW_KEYWORDS:
        if keyword in combined_text:
            logger.debug(f"Selected SIDE view due to keyword: '{keyword}'")
            return CharacterView.SIDE
    
    # Check for explicit front view indicators
    for keyword in FRONT_VIEW_KEYWORDS:
        if keyword in combined_text:
            logger.debug(f"Selected FRONT view due to keyword: '{keyword}'")
            return CharacterView.FRONT
    
    # Default to front view
    logger.debug("Defaulting to FRONT view (no specific indicators found)")
    return CharacterView.FRONT


def get_character_expression_for_shot(
    shot_description: str,
    script_context: Optional[str] = None,
    scene_mood: Optional[str] = None,
) -> CharacterExpression:
    """Determine which facial expression to use based on shot context.
    
    Args:
        shot_description: Description of the shot/scene
        script_context: Optional broader script/story context
        scene_mood: Optional mood of the scene
        
    Returns:
        CharacterExpression enum (NEUTRAL, HAPPY, or SAD)
    """
    # Combine all text for analysis
    text_parts = [shot_description]
    if script_context:
        text_parts.append(script_context)
    if scene_mood:
        text_parts.append(scene_mood)
    
    combined_text = " ".join(text_parts).lower()
    
    # Count keyword matches for each expression
    happy_score = sum(1 for kw in HAPPY_EXPRESSION_KEYWORDS if kw in combined_text)
    sad_score = sum(1 for kw in SAD_EXPRESSION_KEYWORDS if kw in combined_text)
    neutral_score = sum(1 for kw in NEUTRAL_EXPRESSION_KEYWORDS if kw in combined_text)
    
    # Select based on highest score
    if happy_score > sad_score and happy_score > neutral_score:
        logger.debug(f"Selected HAPPY expression (score: {happy_score})")
        return CharacterExpression.HAPPY
    elif sad_score > happy_score and sad_score > neutral_score:
        logger.debug(f"Selected SAD expression (score: {sad_score})")
        return CharacterExpression.SAD
    
    # Default to neutral
    logger.debug(f"Selected NEUTRAL expression (default)")
    return CharacterExpression.NEUTRAL


def get_character_view_and_expression(
    shot_description: str,
    camera_angle: Optional[str] = None,
    character_action: Optional[str] = None,
    script_context: Optional[str] = None,
    scene_mood: Optional[str] = None,
) -> Tuple[CharacterView, CharacterExpression]:
    """Get both view and expression for a character in a shot.
    
    Args:
        shot_description: Description of the shot
        camera_angle: Optional camera angle
        character_action: Optional character action
        script_context: Optional script context
        scene_mood: Optional scene mood
        
    Returns:
        Tuple of (CharacterView, CharacterExpression)
    """
    view = get_character_view_for_shot(shot_description, camera_angle, character_action)
    expression = get_character_expression_for_shot(shot_description, script_context, scene_mood)
    
    # If back view, expression doesn't matter (no face visible)
    # but we still return it for logging/debugging
    if view == CharacterView.BACK:
        logger.debug("Back view selected - expression will not be visible")
    
    return view, expression


def get_portrait_path_for_shot(
    character_id: str,
    registry: CharacterSheetRegistry,
    shot_description: str,
    camera_angle: Optional[str] = None,
    character_action: Optional[str] = None,
    script_context: Optional[str] = None,
    scene_mood: Optional[str] = None,
) -> Optional[str]:
    """Get the appropriate portrait path for a character in a specific shot.
    
    This is the main function to use for selecting character portraits
    based on shot context.
    
    Args:
        character_id: ID of the character
        registry: CharacterSheetRegistry containing all character sheets
        shot_description: Description of the shot
        camera_angle: Optional camera angle
        character_action: Optional character action
        script_context: Optional script context
        scene_mood: Optional scene mood
        
    Returns:
        Path to the appropriate portrait image, or None if not found
    """
    view, expression = get_character_view_and_expression(
        shot_description,
        camera_angle,
        character_action,
        script_context,
        scene_mood,
    )
    
    path = registry.get_portrait_path(character_id, view, expression)
    
    if path:
        logger.debug(f"Selected portrait for {character_id}: {view.value}_{expression.value}")
    else:
        logger.warning(f"No portrait found for {character_id} with {view.value}_{expression.value}")
    
    return path


def get_portrait_path_from_legacy_registry(
    character_id: str,
    legacy_registry: Dict[str, Dict],
    shot_description: str,
    camera_angle: Optional[str] = None,
    character_action: Optional[str] = None,
) -> Optional[str]:
    """Get portrait path from a legacy format registry.
    
    Legacy format:
    {
        "CharacterName": {
            "front": {"path": "...", "description": "..."},
            "side": {"path": "...", "description": "..."},
            "back": {"path": "...", "description": "..."}
        }
    }
    
    Args:
        character_id: ID of the character
        legacy_registry: Legacy format registry dict
        shot_description: Description of the shot
        camera_angle: Optional camera angle
        character_action: Optional character action
        
    Returns:
        Path to the appropriate portrait, or None if not found
    """
    if character_id not in legacy_registry:
        logger.warning(f"Character {character_id} not in registry")
        return None
    
    char_data = legacy_registry[character_id]
    
    # Get the appropriate view
    view = get_character_view_for_shot(shot_description, camera_angle, character_action)
    
    # Try to get the requested view
    view_data = char_data.get(view.value)
    
    if view_data:
        if isinstance(view_data, dict):
            return view_data.get("path")
        return str(view_data)
    
    # Fall back to front view
    front_data = char_data.get("front", char_data.get(CharacterView.FRONT.value))
    if front_data:
        if isinstance(front_data, dict):
            return front_data.get("path")
        return str(front_data)
    
    return None


def analyze_shot_for_characters(
    shot_description: str,
    characters: List[str],
) -> Dict[str, Tuple[CharacterView, CharacterExpression]]:
    """Analyze a shot and determine view/expression for each character.
    
    Args:
        shot_description: Description of the shot
        characters: List of character IDs present in the shot
        
    Returns:
        Dict mapping character_id to (view, expression) tuple
    """
    result = {}
    
    # For now, use the same view/expression for all characters
    # (Could be enhanced to detect per-character context)
    view = get_character_view_for_shot(shot_description)
    expression = get_character_expression_for_shot(shot_description)
    
    for char_id in characters:
        # Check if shot mentions this specific character with different context
        char_pattern = re.compile(
            rf'\b{re.escape(char_id)}\b[^.]*',
            re.IGNORECASE
        )
        char_match = char_pattern.search(shot_description)
        
        if char_match:
            # Character-specific context found
            char_context = char_match.group(0)
            char_view = get_character_view_for_shot(char_context)
            char_expr = get_character_expression_for_shot(char_context)
            result[char_id] = (char_view, char_expr)
        else:
            # Use scene-wide context
            result[char_id] = (view, expression)
    
    return result


# Convenience functions for getting specific view paths
def get_front_portrait_path(
    character_id: str,
    registry: Dict[str, Dict],
    expression: CharacterExpression = CharacterExpression.NEUTRAL,
) -> Optional[str]:
    """Get front view portrait path."""
    char_data = registry.get(character_id, {})
    front_data = char_data.get("front", {})
    
    if isinstance(front_data, dict):
        # Check for expression-specific path
        expr_data = front_data.get(expression.value)
        if expr_data:
            return expr_data.get("path") if isinstance(expr_data, dict) else str(expr_data)
        # Fall back to direct path
        return front_data.get("path")
    return str(front_data) if front_data else None


def get_side_portrait_path(
    character_id: str,
    registry: Dict[str, Dict],
    expression: CharacterExpression = CharacterExpression.NEUTRAL,
) -> Optional[str]:
    """Get side view portrait path."""
    char_data = registry.get(character_id, {})
    side_data = char_data.get("side", {})
    
    if isinstance(side_data, dict):
        expr_data = side_data.get(expression.value)
        if expr_data:
            return expr_data.get("path") if isinstance(expr_data, dict) else str(expr_data)
        return side_data.get("path")
    return str(side_data) if side_data else None


def get_back_portrait_path(
    character_id: str,
    registry: Dict[str, Dict],
) -> Optional[str]:
    """Get back view portrait path (expression doesn't apply)."""
    char_data = registry.get(character_id, {})
    back_data = char_data.get("back", {})
    
    if isinstance(back_data, dict):
        # For back view, use neutral or any available
        for key in ["neutral", "path"]:
            data = back_data.get(key)
            if data:
                return data.get("path") if isinstance(data, dict) else str(data)
    return str(back_data) if back_data else None
