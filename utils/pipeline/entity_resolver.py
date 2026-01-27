import os
import re
from typing import Dict, List, Optional, Tuple

from utils.pipeline.s3_loader import S3CharacterLoader
from utils.media.image import download_image
from interfaces import CharacterInScene
from interfaces.entities.brand_context import BrandContext, GameContext


TAG_PATTERN = re.compile(r"@(?P<key>brand|game|character):(?P<value>[^\s,;]+)", re.IGNORECASE)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _contains_match(texts: List[str], *candidates: str) -> bool:
    merged = _normalize(" ".join([t or "" for t in texts]))
    for candidate in candidates:
        if not candidate:
            continue
        if _normalize(candidate) in merged:
            return True
    return False


def _parse_tags(texts: List[str]) -> Tuple[Optional[str], Optional[str], List[str]]:
    brand_hint = None
    game_hint = None
    characters: List[str] = []
    for text in texts:
        if not text:
            continue
        for match in TAG_PATTERN.finditer(text):
            key = match.group("key").lower()
            value = match.group("value").strip()
            if key == "brand":
                brand_hint = value
            elif key == "game":
                game_hint = value
            elif key == "character":
                characters.append(value)
    return brand_hint, game_hint, characters


def _build_context_block(brand_data: Optional[Dict], game_data: Optional[Dict]) -> str:
    parts = []
    if brand_data:
        parts.append("Brand Context:")
        parts.append(f"- Brand: {brand_data.get('name', brand_data.get('id'))}")
        if brand_data.get("description"):
            parts.append(f"- Description: {brand_data['description']}")
        if brand_data.get("brand_story"):
            parts.append(f"- Brand Story: {brand_data['brand_story']}")
        if brand_data.get("series_name"):
            parts.append(f"- Series: {brand_data['series_name']}")
        if brand_data.get("series_concept"):
            parts.append(f"- Series Concept: {brand_data['series_concept']}")
        # Include look and feel if available
        look_and_feel = brand_data.get("look_and_feel")
        if look_and_feel and isinstance(look_and_feel, dict):
            if look_and_feel.get("visuals"):
                parts.append(f"- Visuals: {look_and_feel['visuals']}")
            if look_and_feel.get("pacing"):
                parts.append(f"- Pacing: {look_and_feel['pacing']}")
            if look_and_feel.get("soundtrack"):
                parts.append(f"- Soundtrack: {look_and_feel['soundtrack']}")
    if game_data:
        parts.append("Game Context:")
        parts.append(f"- Game: {game_data.get('name', game_data.get('id'))}")
        if game_data.get("description"):
            parts.append(f"- Description: {game_data['description']}")
        if game_data.get("genre"):
            parts.append(f"- Genre: {game_data['genre']}")
        if game_data.get("gameplay_summary"):
            parts.append(f"- Gameplay: {game_data['gameplay_summary']}")
    return "\n".join(parts).strip()


def _build_character_profiles_block(characters: Optional[List[CharacterInScene]]) -> str:
    """Build a rich context block for character profiles.
    
    This block includes personality, voice, role, and traits for each character,
    enabling agents to generate personality-consistent content.
    """
    if not characters:
        return ""
    
    lines = ["<CHARACTER_PROFILES>"]
    for char in characters:
        lines.append(f"\n{char.identifier_in_scene}:")
        if char.description:
            lines.append(f"  Description: {char.description}")
        if char.personality:
            lines.append(f"  Personality: {char.personality}")
        if char.voice_description:
            lines.append(f"  Voice: {char.voice_description}")
        if char.role:
            lines.append(f"  Role: {char.role}")
        if char.traits:
            lines.append(f"  Traits: {', '.join(char.traits)}")
        if char.appearance:
            lines.append(f"  Appearance: {char.appearance}")
        if char.static_features:
            lines.append(f"  Visual Features: {char.static_features}")
    lines.append("</CHARACTER_PROFILES>")
    return "\n".join(lines)


def _build_brand_context(
    brand_id: str,
    brand_data: Dict,
    characters: Optional[List[CharacterInScene]] = None,
    logo_url: Optional[str] = None,
) -> BrandContext:
    """Build a BrandContext from S3 data for ideation."""
    # Convert CharacterInScene to dict format for BrandContext
    char_dicts = []
    if characters:
        for char in characters:
            char_dicts.append({
                "name": char.identifier_in_scene,
                "role": char.role,
                "personality": char.personality,
                "description": char.description,
                "traits": char.traits,
            })
    
    return BrandContext.from_s3_data(
        brand_id=brand_id,
        brand_data=brand_data,
        characters=char_dicts,
        logo_url=logo_url,
    )


def _build_game_context(
    game_id: str,
    game_data: Dict,
    characters: Optional[List[CharacterInScene]] = None,
    icon_url: Optional[str] = None,
) -> GameContext:
    """Build a GameContext from S3 data for ideation."""
    # Convert CharacterInScene to dict format for GameContext
    char_dicts = []
    if characters:
        for char in characters:
            char_dicts.append({
                "name": char.identifier_in_scene,
                "role": char.role,
                "personality": char.personality,
                "description": char.description,
                "traits": char.traits,
            })
    
    return GameContext.from_s3_data(
        game_id=game_id,
        game_data=game_data,
        characters=char_dicts,
        icon_url=icon_url,
    )


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _safe_download(url: str, path: str) -> Optional[str]:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        download_image(url, path)
        if os.path.exists(path):
            return path
    except Exception:
        return None
    return None


def _resolve_logo_paths(
    loader: S3CharacterLoader,
    brand_id: Optional[str],
    brand_data: Optional[Dict],
    game_id: Optional[str],
    game_data: Optional[Dict],
    working_dir: Optional[str],
) -> List[Dict[str, str]]:
    if not working_dir:
        return []
    reference_images: List[Dict[str, str]] = []
    base_url = loader.config.base_url

    if brand_id and brand_data:
        logo_path = (
            brand_data.get("media", {})
            .get("logo", {})
            .get("primary")
        )
        if logo_path:
            url = logo_path if _is_url(logo_path) else f"{base_url}/brands/{brand_id}/{logo_path}"
            local_path = os.path.join(working_dir, "brand_assets", "brand_logo.png")
            downloaded = _safe_download(url, local_path)
            if downloaded:
                reference_images.append(
                    {
                        "path": downloaded,
                        "description": f"{brand_data.get('name', brand_id)} brand logo",
                    }
                )
        # Fallback: try standard logo locations if not specified in brand.json
        if not any("brand logo" in r.get("description", "").lower() for r in reference_images):
            for logo_filename in [
                "logo.png",
                "Logo.png",
                "icon.png",
                "Icon.png",
                "logo.jpg",
                "Logo.jpg",
                "icon.jpg",
                "Icon.jpg",
            ]:
                url = f"{base_url}/brands/{brand_id}/{logo_filename}"
                local_path = os.path.join(working_dir, "brand_assets", "brand_logo.png")
                downloaded = _safe_download(url, local_path)
                if downloaded:
                    reference_images.append(
                        {
                            "path": downloaded,
                            "description": f"{brand_data.get('name', brand_id)} brand logo",
                        }
                    )
                    break

    if game_id:
        game_name = game_data.get("name", game_id) if game_data else game_id
        icon_downloaded = False
        
        # First try from game.json media.icon.primary
        if game_data:
            icon_path = (
                game_data.get("media", {})
                .get("icon", {})
                .get("primary")
            )
            if icon_path:
                url = icon_path if _is_url(icon_path) else f"{base_url}/games/{game_id}/{icon_path}"
                local_path = os.path.join(working_dir, "brand_assets", "game_icon.png")
                downloaded = _safe_download(url, local_path)
                if downloaded:
                    reference_images.append(
                        {
                            "path": downloaded,
                            "description": f"{game_name} game icon",
                        }
                    )
                    icon_downloaded = True
        
        # Fallback: try standard icon locations if not found in game.json
        if not icon_downloaded:
            for icon_filename in [
                "icon.png",
                "Icon.png",
                "logo.png",
                "Logo.png",
                "icon.jpg",
                "Icon.jpg",
                "logo.jpg",
                "Logo.jpg",
            ]:
                url = f"{base_url}/games/{game_id}/{icon_filename}"
                local_path = os.path.join(working_dir, "brand_assets", "game_icon.png")
                downloaded = _safe_download(url, local_path)
                if downloaded:
                    reference_images.append(
                        {
                            "path": downloaded,
                            "description": f"{game_name} game icon",
                        }
                    )
                    break

    return reference_images


def resolve_s3_entities(
    texts: List[str],
    brand_hint: Optional[str] = None,
    game_hint: Optional[str] = None,
    working_dir: Optional[str] = None,
):
    loader = S3CharacterLoader()
    tag_brand, tag_game, tag_chars = _parse_tags(texts)
    brand_hint = brand_hint or tag_brand
    game_hint = game_hint or tag_game

    brand_id = None
    brand_data = None
    for candidate in loader.list_brands():
        data = loader.load_brand_json(candidate) or {}
        name = data.get("name", candidate)
        if brand_hint and _normalize(brand_hint) == _normalize(candidate):
            brand_id, brand_data = candidate, data
            break
        if brand_hint and _normalize(brand_hint) == _normalize(name):
            brand_id, brand_data = candidate, data
            break
    if not brand_id:
        for candidate in loader.list_brands():
            data = loader.load_brand_json(candidate) or {}
            name = data.get("name", candidate)
            if _contains_match(texts, candidate, name):
                brand_id, brand_data = candidate, data
                break

    game_id = None
    game_data = None
    for candidate in loader.list_games():
        data = loader.load_game_json(candidate) or {}
        name = data.get("name", candidate)
        if game_hint and _normalize(game_hint) == _normalize(candidate):
            game_id, game_data = candidate, data
            break
        if game_hint and _normalize(game_hint) == _normalize(name):
            game_id, game_data = candidate, data
            break
    if not game_id:
        for candidate in loader.list_games():
            data = loader.load_game_json(candidate) or {}
            name = data.get("name", candidate)
            if _contains_match(texts, candidate, name):
                game_id, game_data = candidate, data
                break

    if game_data and not brand_id:
        brand_id = game_data.get("brand")
        if brand_id:
            brand_data = loader.load_brand_json(brand_id) or {}

    selected_identifiers = list(dict.fromkeys(tag_chars))

    characters = None
    portrait_registry = None
    if game_id:
        game_chars = loader.load_game_characters(game_id, selected_identifiers or None)
        characters = loader.to_vimax_characters(game_chars, selected_identifiers or None)
        download_dir = os.path.join(working_dir, "s3_characters") if working_dir else None
        portrait_registry = loader.to_vimax_portrait_registry(game_chars, download_dir=download_dir)
    elif brand_id:
        brand_chars = loader.load_brand_characters(brand_id, selected_identifiers or None)
        characters = loader.to_vimax_characters(brand_chars, selected_identifiers or None)
        download_dir = os.path.join(working_dir, "s3_characters") if working_dir else None
        portrait_registry = loader.to_vimax_portrait_registry(brand_chars, download_dir=download_dir)

    context_block = _build_context_block(brand_data, game_data)
    character_profiles_block = _build_character_profiles_block(characters)
    
    # Combine brand/game context with character profiles
    full_context_block = context_block
    if character_profiles_block:
        if full_context_block:
            full_context_block = f"{full_context_block}\n\n{character_profiles_block}"
        else:
            full_context_block = character_profiles_block
    
    reference_images = _resolve_logo_paths(
        loader=loader,
        brand_id=brand_id,
        brand_data=brand_data,
        game_id=game_id,
        game_data=game_data,
        working_dir=working_dir,
    )

    # Build structured context objects for ideation
    brand_context: Optional[BrandContext] = None
    game_context: Optional[GameContext] = None
    
    if brand_id and brand_data:
        logo_url = None
        logo_path = brand_data.get("media", {}).get("logo", {}).get("primary")
        if logo_path:
            if _is_url(logo_path):
                logo_url = logo_path
            else:
                logo_url = f"{loader.config.base_url}/brands/{brand_id}/{logo_path}"
        
        brand_context = _build_brand_context(
            brand_id=brand_id,
            brand_data=brand_data,
            characters=characters,
            logo_url=logo_url,
        )
    
    if game_id and game_data:
        icon_url = None
        icon_path = game_data.get("media", {}).get("icon", {}).get("primary")
        if icon_path:
            if _is_url(icon_path):
                icon_url = icon_path
            else:
                icon_url = f"{loader.config.base_url}/games/{game_id}/{icon_path}"
        
        game_context = _build_game_context(
            game_id=game_id,
            game_data=game_data,
            characters=characters,
            icon_url=icon_url,
        )

    return {
        "brand_id": brand_id,
        "brand_data": brand_data,
        "game_id": game_id,
        "game_data": game_data,
        "characters": characters,
        "portrait_registry": portrait_registry,
        "context_block": full_context_block,
        "character_profiles_block": character_profiles_block,
        "reference_images": reference_images,
        # Structured context objects for ideation
        "brand_context": brand_context,
        "game_context": game_context,
    }
