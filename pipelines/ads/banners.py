"""
Idea to Ad Banners Pipeline

Generates high-converting ad banner images for brands and games.
Supports S3 entity resolution (brands, games, and characters),
trend-based variants, and multiple IAB/Google/Meta sizes. 
Targets 25%+ CTR with creative, trend, and conversion-focused variants.

Character support: Characters from S3 can be featured in banners
for consistent brand mascot representation.
"""

import json
import logging
import os
import re
import asyncio
from typing import Optional, Dict, Any, List, Literal, Tuple

import yaml
import importlib
from PIL import Image
from langchain.chat_models import init_chat_model

from agents.planners.marketing import AdBannerIdeator, BannerConcept, BannerIdeationResult
from agents.producers.visuals import StoryboardArtist
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from utils.media.image import composite_character_on_image, composite_multiple_characters, composite_logo_on_image
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.output.monetization import TrendContext
from interfaces.entities.character import CharacterInScene


# ---------------------------------------------------------------------------
# Standard ad banner sizes (IAB, Google Display, Meta)
# (name, width, height, aspect_ratio for image gen - closest match for PiAPI)
# ---------------------------------------------------------------------------
AD_BANNER_SIZES = {
    "medium_rectangle": (300, 250, "6:5"),      # 300x250, IAB
    "large_rectangle": (336, 280, "6:5"),       # 336x280
    "leaderboard": (728, 90, "8:1"),            # 728x90
    "wide_skyscraper": (160, 600, "4:15"),      # 160x600, use 9:16 then crop
    "half_page": (300, 600, "1:2"),             # 300x600, ~9:16
    "mobile_banner": (320, 50, "32:5"),          # 320x50, use 16:9 then crop
    "billboard": (970, 250, "97:25"),           # 970x250, ~4:1, use 16:9 then crop
    "facebook_landscape": (1200, 628, "2:1"),   # 1200x628
    "square_social": (1080, 1080, "1:1"),       # 1080x1080
    "portrait_story": (1080, 1350, "4:5"),      # 1080x1350, Stories
}

# Aspect ratios PiAPI typically supports; map our ratio to nearest
ASPECT_RATIO_TO_PIAPI = {
    "1:1": "1:1",
    "2:1": "2:1",
    "4:5": "4:5",
    "6:5": "4:3",   # close
    "8:1": "16:9",  # very wide, use 16:9 and crop
    "4:15": "9:16", # tall, 9:16
    "1:2": "9:16",
    "32:5": "16:9",
    "97:25": "16:9",
}


def _aspect_to_piapi(ratio: str) -> str:
    return ASPECT_RATIO_TO_PIAPI.get(ratio, "16:9")


def _resize_to_exact(img_path: str, width: int, height: int, out_path: str) -> None:
    """Resize image to exact (width, height); center-crop if aspect differs."""
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    target_r = width / height
    current_r = w / h
    if abs(current_r - target_r) < 0.05:
        resized = img.resize((width, height), Image.Resampling.LANCZOS)
    else:
        if current_r > target_r:
            new_w = int(h * target_r)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
            new_h = int(w / target_r)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))
        resized = img.resize((width, height), Image.Resampling.LANCZOS)
    resized.save(out_path)


class AdBannersPipeline:
    """Pipeline to generate high-converting ad banner images for brands and games."""

    def __init__(
        self,
        chat_model,
        image_generator=None,
        working_dir: str = ".working_dir/ad_banners",
        trend_analyzer: Optional[TrendAnalyzer] = None,
        force_regenerate: bool = False,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.trend_analyzer = trend_analyzer
        self.force_regenerate = force_regenerate

        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="ad_banners",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.ideator = AdBannerIdeator(chat_model=self.chat_model)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, pipeline_kind="ad")
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="ad_banners", run_id=self.run_id, local_dir=self.working_dir)

    @classmethod
    def init_from_config(cls, config_path: str) -> "AdBannersPipeline":
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), "..", ".."))

        def _resolve_env(v):
            if not isinstance(v, str):
                return v
            if v.startswith("${") and v.endswith("}"):
                return os.getenv(v[2:-1], "")
            if v.startswith("ENV:"):
                return os.getenv(v[4:], "")
            return v

        def _resolve_path(p):
            if not p:
                return None
            return p if os.path.isabs(p) else os.path.join(base_dir, p)

        chat_model_args = {k: _resolve_env(v) for k, v in config["chat_model"]["init_args"].items()}
        chat_model = init_chat_model(**chat_model_args)

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        image_generator, _ = create_generators_from_config(config)  # Only need image generator for banners

        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            working_dir=_resolve_path(config["working_dir"]) or config["working_dir"],
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
        )

    def _build_entity_context(
        self,
        resolution: Dict,
        brand_id: Optional[str],
        game_id: Optional[str],
    ) -> str:
        """Build rich entity context from S3 resolution for the ideator."""
        parts = []
        b = resolution.get("brand_data") or {}
        g = resolution.get("game_data") or {}
        if game_id and g:
            parts.append(f"Game: {g.get('name', game_id)}. {g.get('description', '')}")
            if g.get("genre"):
                parts.append(f"Genre: {g['genre']}.")
            if g.get("gameplay_summary"):
                parts.append(f"Gameplay: {g['gameplay_summary']}")
        if brand_id and b:
            parts.append(f"Brand: {b.get('name', brand_id)}. {b.get('description', '')}")
            if b.get("brand_story"):
                parts.append(f"Brand story: {b['brand_story']}")
        return " ".join(parts).strip() or ""

    async def _generate_banner_image(
        self,
        concept: BannerConcept,
        size_name: str,
        width: int,
        height: int,
        aspect_ratio: str,
        logo_path: Optional[str],
        out_dir: str,
        entity_name: str,
        character_portraits: Optional[Dict[str, Any]] = None,
        characters: Optional[List[CharacterInScene]] = None,
        feature_characters: bool = True,
    ) -> Optional[str]:
        """Generate one banner image for a concept and size."""
        if not self.image_generator:
            return None

        # Build prompt with character mentions
        character_prompt_part = ""
        visible_chars = []
        if characters and character_portraits:
            for char in characters:
                char_name = char.identifier_in_scene
                if not char_name:
                    continue
                pattern = rf"(?i)\b({re.escape(char_name)}|<{re.escape(char_name)}>)\b"
                if re.search(pattern, concept.visual_prompt):
                    visible_chars.append(char)
                    if char.static_features:
                        character_prompt_part += f" {char_name}: {char.static_features[:100]}."

        # Base Prompt
        prompt = f"""High-converting ad banner for {entity_name}. {concept.visual_prompt}{character_prompt_part}
Headline: "{concept.headline}". CTA: "{concept.cta_copy}".
Style: {concept.style}, professional, bold, high contrast. {concept.color_direction or 'Vibrant, thumb-stopping colors.'}
Suitable for display and social ad campaigns. No watermarks. Clean, conversion-optimized composition."""

        piapi_ratio = _aspect_to_piapi(aspect_ratio)
        final_path = os.path.join(out_dir, f"{size_name}_{width}x{height}.png")
        composite_path = os.path.join(out_dir, f"composite_{size_name}.png")
        raw_output_path = os.path.join(out_dir, f"raw_{size_name}.png")
        bg_path = os.path.join(out_dir, f"bg_{size_name}.png")

        try:
            # TRACK 1: BACKGROUND GENERATION
            bg_prompt = prompt
            for char in visible_chars:
                bg_prompt = bg_prompt.replace(char.identifier_in_scene, "the focal area")
            bg_prompt += " EMPTY CINEMATIC ENVIRONMENT. No characters, no people, no robots, no figures. Background only."
            
            # Save debug prompt
            debug_dir = os.path.join(out_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, f"{size_name}_bg_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(bg_prompt)

            bg_out = await self.image_generator.generate_single_image(
                prompt=bg_prompt,
                aspect_ratio=piapi_ratio,
            )
            bg_out.save(bg_path)

            # Resize background to final dimensions for the composite version
            _resize_to_exact(bg_path, width, height, composite_path)

            # TRACK 2: COMPOSITE CHARACTERS & LOGO (for perfect preservation)
            if feature_characters and visible_chars and character_portraits:
                self._composite_characters_on_banner(
                    banner_path=composite_path,
                    visible_characters=visible_chars,
                    character_portraits=character_portraits,
                    visual_direction=concept.visual_prompt,
                    width=width,
                    height=height,
                )
            
            if logo_path and os.path.exists(logo_path):
                composite_logo_on_image(
                    background_path=composite_path,
                    logo_path=logo_path,
                    output_path=composite_path,
                    position="top-left",
                    scale_factor=0.12,
                    auto_remove_bg=True
                )

            # TRACK 3: RAW GENERATION (Gelling it all together)
            # We use the composite as the main reference to "gel" everything into the final scene.
            char_context = " Featuring " + ", ".join([c.identifier_in_scene for c in visible_chars]) if visible_chars else ""
            logo_context = " with integrated brand logo/icon" if logo_path else ""
            
            raw_prompt = f"""{prompt}.{char_context}{logo_context}.
High quality professional ad banner, expressive characters gelled into scene. 
Blend characters and brand assets naturally into environment. No extra text, no collages."""

            with open(os.path.join(debug_dir, f"{size_name}_raw_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(raw_prompt)

            # Build raw references: the composite frame + logo + character portraits for consistency
            raw_refs = [composite_path]
            if logo_path and os.path.exists(logo_path):
                raw_refs.append(logo_path)
                
            if visible_chars and character_portraits:
                for char in visible_chars[:2]:
                    char_id = char.identifier_in_scene
                    if char_id in character_portraits:
                        front_info = character_portraits[char_id].get("front", {})
                        path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                        if path and os.path.exists(path) and path not in raw_refs:
                            raw_refs.append(path)

            img_out = await self.image_generator.generate_single_image(
                prompt=raw_prompt,
                reference_image_paths=raw_refs,
                aspect_ratio=piapi_ratio,
                strength=0.55, # Sufficient strength to gel while keeping placement
            )
            img_out.save(raw_output_path)

            # The final version is the one resized to exact specs from the gelled raw output
            _resize_to_exact(raw_output_path, width, height, final_path)
            
            return final_path
        except Exception as e:
            self.logger.warning(f"Banner image failed {concept.style} {size_name}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def _composite_characters_on_banner(
        self,
        banner_path: str,
        visible_characters: List[CharacterInScene],
        character_portraits: Dict[str, Any],
        visual_direction: str,
        width: int,
        height: int,
    ) -> None:
        """Composite character portraits onto a banner image."""
        if not visible_characters or not os.path.exists(banner_path):
            return
        
        # Smart view/expression selection
        view = get_character_view_for_shot(visual_direction)
        expr = get_character_expression_for_shot(visual_direction)
        
        portraits_to_composite = []
        for char in visible_characters:
            char_id = char.identifier_in_scene
            if char_id in character_portraits:
                char_path = None
                # Try specific view
                view_data = character_portraits[char_id].get(view.value, {})
                if isinstance(view_data, dict):
                    # Try specific expression
                    expr_data = view_data.get(expr.value, {})
                    char_path = expr_data.get("path") if isinstance(expr_data, dict) else expr_data
                    if not char_path:
                        char_path = view_data.get("path")
                else:
                    char_path = str(view_data)
                
                # Fallback to front
                if not char_path:
                    front_info = character_portraits[char_id].get("front", {})
                    char_path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                
                if char_path and os.path.exists(char_path):
                    portraits_to_composite.append(char_path)
        
        if not portraits_to_composite:
            return
        
        try:
            aspect = width / height
            scale = 0.25 if aspect > 3 else (0.35 if aspect > 1.5 else 0.4)
            
            if len(portraits_to_composite) == 1:
                composite_character_on_image(
                    background_path=banner_path,
                    character_path=portraits_to_composite[0],
                    output_path=banner_path,
                    position="right",
                    scale_factor=scale,
                    vertical_offset=0.0,
                    blend_mode="soft",
                )
            else:
                composite_multiple_characters(
                    background_path=banner_path,
                    character_paths=portraits_to_composite[:2],
                    output_path=banner_path,
                    scale_factors=[scale * 0.9] * min(len(portraits_to_composite), 2),
                )
        except Exception as e:
            self.logger.warning(f"Failed to composite characters on banner: {e}")

    async def __call__(
        self,
        brand_or_game: str,
        entity_type: Literal["brand", "game"] = "brand",
        brief: str = "",
        audience: str = "General mobile and desktop users, 18–44",
        campaign_goal: str = "Conversions and installs",
        platforms: str = "Google Display, Meta (Facebook/Instagram), programmatic",
        trendy: bool = False,
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_ids: Optional[List[str]] = None,
        characters: Optional[List[CharacterInScene]] = None,
        character_portraits_registry: Optional[Dict[str, Any]] = None,
        feature_characters_in_banners: bool = True,
        num_concepts: int = 5,
        sizes: Optional[List[str]] = None,
        additional: str = "",
    ) -> Dict[str, Any]:
        """
        Generate high-converting ad banner images.

        Args:
            brand_or_game: Brand or game name (used if S3 not resolved)
            entity_type: "brand" or "game"
            brief: Campaign/banner brief
            audience: Target audience
            campaign_goal: Campaign objective
            platforms: Ad platforms
            trendy: Use trend analyzer for trend-based concepts
            brand_id: S3 brand id (e.g. intelli-verse-x)
            game_id: S3 game id (e.g. quiz-verse)
            character_ids: S3 character ids to feature in banners (e.g. ["max-the-robot", "curio"])
            characters: Pre-built CharacterInScene objects for banner generation
            character_portraits_registry: Pre-built character portrait registry {char_id: {"front": {"path": ...}}}
            feature_characters_in_banners: If True, composite characters onto banner images
            num_concepts: Number of concepts (min 3)
            sizes: Subset of AD_BANNER_SIZES keys; None = all
            additional: Extra instructions for ideator

        Returns:
            Dict with run_id, ideation, banners by size and style, paths, and manifest.
        """
        output_path = os.path.join(self.working_dir, "adbanners_output.json")
        if os.path.exists(output_path) and not self.force_regenerate:
            with open(output_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # --- S3 resolution ---
        resolution = {}
        entity_context = ""
        logo_path = None
        local_character_portraits: Dict[str, Any] = character_portraits_registry or {}
        local_characters: List[CharacterInScene] = characters or []
        
        if brand_id or game_id or character_ids:
            texts = []
            if game_id:
                texts.append(f"@game:{game_id}")
            if brand_id:
                texts.append(f"@brand:{brand_id}")
            # Add character references for S3 resolution
            for char_id in (character_ids or []):
                texts.append(f"@character:{char_id}")
            if not texts:
                texts = [f"@{entity_type}:{brand_or_game}"]
            resolution = resolve_s3_entities(
                texts=texts,
                brand_hint=brand_id,
                game_hint=game_id,
                working_dir=self.working_dir,
            )
            entity_context = self._build_entity_context(resolution, brand_id, game_id)
            for ref in resolution.get("reference_images") or []:
                p = ref.get("path")
                d = (ref.get("description") or "").lower()
                if p and os.path.exists(p):
                    # Robust logo/icon detection
                    is_logo = any(kw in d for kw in ["logo", "icon", "brand asset", "app icon", "game icon"])
                    if is_logo:
                        logo_path = p
                        # Prefer game icon for game ads
                        if entity_type == "game" and "icon" in d:
                            break
                        # Prefer brand logo for brand ads
                        if entity_type == "brand" and "logo" in d:
                            break
            
            # Fallback: if no logo found in reference_images but resolution has brand/game data with icon/logo
            if not logo_path:
                if entity_type == "game" and resolution.get("game_data", {}).get("icon_url"):
                    # resolve_s3_entities should have downloaded it to brand_assets
                    icon_p = os.path.join(self.working_dir, "brand_assets", "game_icon.png")
                    if os.path.exists(icon_p):
                        logo_path = icon_p
                elif entity_type == "brand" and resolution.get("brand_data", {}).get("logo_url"):
                    logo_p = os.path.join(self.working_dir, "brand_assets", "brand_logo.png")
                    if os.path.exists(logo_p):
                        logo_path = logo_p

            if resolution.get("game_data"):
                brand_or_game = resolution["game_data"].get("name", brand_or_game)
            elif resolution.get("brand_data"):
                brand_or_game = resolution["brand_data"].get("name", brand_or_game)
            
        # Extract character portraits from S3 resolution
        s3_chars_dir = os.path.join(self.working_dir, "s3_characters")
        if os.path.exists(s3_chars_dir):
            for char_folder in os.listdir(s3_chars_dir):
                char_path = os.path.join(s3_chars_dir, char_folder)
                if os.path.isdir(char_path):
                    # Smart view resolution
                    char_entry = {}
                    views_to_check = ["front_neutral", "front_reference", "front", "side_neutral", "back_neutral"]
                    for view in views_to_check:
                        for ext in [".png", ".jpg", ".jpeg"]:
                            p = os.path.join(char_path, f"{view}{ext}")
                            if os.path.exists(p):
                                # Map internal view name to standard keys
                                key = "front" if "front" in view else view.split("_")[0]
                                char_entry[key] = {"path": p, "description": f"{view} of {char_folder}"}
                                break
                    
                    # Ensure we have at least a 'front' view
                    if "front" not in char_entry:
                        for f in os.listdir(char_path):
                            if "front" in f.lower() and f.lower().endswith(('.png', '.jpg', '.jpeg')):
                                char_entry["front"] = {"path": os.path.join(char_path, f), "description": f"Front portrait of {char_folder}"}
                                break
                    
                    # Final fallback for 'front' if still missing
                    if "front" not in char_entry:
                        for f in os.listdir(char_path):
                            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                                char_entry["front"] = {"path": os.path.join(char_path, f), "description": f"Portrait of {char_folder}"}
                                break

                    if char_entry:
                        local_character_portraits[char_folder] = char_entry
                        # Also create CharacterInScene if not already provided
                        if not any(c.identifier_in_scene == char_folder for c in local_characters):
                            # Read metadata if available
                            metadata_path = os.path.join(char_path, "metadata.json")
                            static_features = ""
                            if os.path.exists(metadata_path):
                                try:
                                    with open(metadata_path, "r") as f:
                                        meta = json.load(f)
                                        static_features = meta.get("description", "")
                                except:
                                    pass
                            local_characters.append(CharacterInScene(
                                idx=len(local_characters),
                                identifier_in_scene=char_folder,
                                static_features=static_features,
                                dynamic_features="",
                                is_visible=True,
                            ))
        
        # Log character setup
        if local_character_portraits:
            self.logger.info(f"Character portraits available for banners: {list(local_character_portraits.keys())}")

        # RESUME CHECK: Ideation
        ideation_path = os.path.join(self.working_dir, "ideation.json")
        if os.path.exists(ideation_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing ideation: {ideation_path}")
            with open(ideation_path, "r", encoding="utf-8") as f:
                ideation_data = json.load(f)
                ideation = BannerIdeationResult(**ideation_data)
        else:
            # --- Trends ---
            trend_block = ""
            if trendy and self.trend_analyzer:
                try:
                    tc = await self.trend_analyzer.fetch_trends(category="advertising", limit=15)
                    trend_block = tc.to_context_block()
                    with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                        json.dump(tc.model_dump(), f, ensure_ascii=False, indent=2)
                except Exception as e:
                    self.logger.warning(f"Trend fetch failed: {e}")

            # --- Ideation ---
            self.logger.info("Running AdBannerIdeator...")
            ideation = await self.ideator.ideate(
                brand_or_game=brand_or_game,
                entity_type=entity_type,
                entity_context=entity_context,
                brief=brief,
                audience=audience,
                campaign_goal=campaign_goal,
                platforms=platforms,
                trend_context=trend_block,
                additional=additional,
                num_concepts=num_concepts,
            )
            os.makedirs(self.working_dir, exist_ok=True)
            with open(ideation_path, "w", encoding="utf-8") as f:
                json.dump(ideation.model_dump(), f, ensure_ascii=False, indent=2)

        # Phase 1 reasoning: rationale behind banner concepts (creative "script" for visuals)
        concepts_summary = "; ".join(f"{c.style}: {c.headline[:40]}…" for c in ideation.concepts[:5])
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="ad_banners",
            phase_label="Phase 1: Banner ideation and concepts",
            content_type="ideation",
            rationale=(
                "Banner concepts act as the creative script for each visual: headline, CTA, visual prompt, and style. "
                "AdBannerIdeator generates multiple concepts (creative, trend, conversion-focused) so we can test "
                "different angles. Entity context (brand/game), campaign goal, and platform constraints shape "
                "thumb-stopping headlines and clear CTAs. Trends are used when trendy=True to align with current themes."
            ),
            inputs={
                "entity_name": ideation.entity_name,
                "entity_type": ideation.entity_type,
                "audience": audience,
                "campaign_goal": campaign_goal,
                "platforms": platforms,
                "entity_context_used": bool(entity_context),
                "trend_context_used": bool(trend_block),
                "num_concepts": len(ideation.concepts),
            },
            outputs={
                "ideation.json": "Banner concepts (headline, CTA, visual_prompt, style) per variant.",
            },
            extra=f"Concepts summary: {concepts_summary}",
        )

        # Director / creative lead reasoning (AdBannerIdeator)
        write_director_reasoning(
            working_dir=self.working_dir,
            pipeline_name="adbanners",
            director_name="AdBannerIdeator",
            rationale=(
                "AdBannerIdeator acts as creative lead: it produces multiple concepts (creative, trend, "
                "conversion) each with headline, CTA, visual_prompt, style, and color_direction. "
                "Entity context (brand/game), campaign_goal, platforms, and trends shape the concepts. "
                "This replaces a separate Director; the ideator's output is the creative brief for the visuals."
            ),
            inputs={"entity_name": ideation.entity_name, "num_concepts": len(ideation.concepts), "campaign_goal": campaign_goal},
            outputs={"ideation.json": "Concepts (headline, CTA, visual_prompt, style) per concept."},
        )

        # --- Sizes to generate ---
        size_names = sizes or list(AD_BANNER_SIZES.keys())
        size_configs = {k: AD_BANNER_SIZES[k] for k in size_names if k in AD_BANNER_SIZES}
        if not size_configs:
            size_configs = {"medium_rectangle": AD_BANNER_SIZES["medium_rectangle"], "facebook_landscape": AD_BANNER_SIZES["facebook_landscape"]}

        # --- Generate banners ---
        banners: List[Dict[str, Any]] = []
        by_size: Dict[str, List[str]] = {s: [] for s in size_configs}
        by_style: Dict[str, List[str]] = {}

        for c in ideation.concepts:
            by_style.setdefault(c.style, [])
            c_dir = os.path.join(self.working_dir, "banners", c.style.replace(" ", "_").lower())
            os.makedirs(c_dir, exist_ok=True)

            for size_name, (w, h, ar) in size_configs.items():
                banner_fname = f"{size_name}_{w}x{h}.png"
                path = os.path.join(c_dir, banner_fname)
                
                # RESUME CHECK: Banner Image
                if os.path.exists(path) and not self.force_regenerate:
                    # No need to regenerate
                    pass
                else:
                    path = await self._generate_banner_image(
                        concept=c,
                        size_name=size_name,
                        width=w,
                        height=h,
                        aspect_ratio=ar,
                        logo_path=logo_path,
                        out_dir=c_dir,
                        entity_name=ideation.entity_name,
                        character_portraits=local_character_portraits,
                        characters=local_characters,
                        feature_characters=feature_characters_in_banners,
                    )
                
                if path and os.path.exists(path):
                    rec = {"style": c.style, "size": size_name, "width": w, "height": h, "path": path, "headline": c.headline, "cta": c.cta_copy}
                    banners.append(rec)
                    by_size[size_name].append(path)
                    by_style[c.style].append(path)

        # --- Manifest ---
        manifest = []
        for b in banners:
            manifest.append({"path": b["path"], "style": b["style"], "size": b["size"], "width": b["width"], "height": b["height"], "headline": b["headline"], "cta": b["cta"]})

        payload = {
            "run_id": self.run_id,
            "entity_name": ideation.entity_name,
            "entity_type": ideation.entity_type,
            "ideation": ideation.model_dump(),
            "banners": banners,
            "by_size": by_size,
            "by_style": by_style,
            "manifest": manifest,
            "sizes_generated": list(size_configs.keys()),
            "characters_featured": [c.identifier_in_scene for c in local_characters] if local_characters else [],
            "character_compositing_enabled": feature_characters_in_banners and bool(local_character_portraits),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3()

        # Cinematographer and picturization reasoning
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="ad_banners",
            rationale=(
                "Picturization: each concept's visual_prompt, headline, CTA, style, and color_direction "
                "drive the banner image. We generate one image per concept and per size (IAB/Google/Meta). "
                "The prompt combines visual_prompt, headline, CTA, style, and optional logo reference. "
                "Framing is determined by the aspect ratio per size; we center-crop to exact dimensions. "
                "Character consistency: S3 characters (or provided character portraits) are composited onto "
                "banners using post-processing when feature_characters_in_banners=True. Characters mentioned "
                "in the visual_prompt are detected using regex word boundaries to avoid false positives. "
                "Character scale is adjusted based on banner aspect ratio (smaller for wide banners)."
            ),
            inputs={
                "sizes_generated": list(size_configs.keys()),
                "banners_count": len(banners),
                "characters_featured": [c.identifier_in_scene for c in local_characters] if local_characters else [],
                "character_compositing_enabled": feature_characters_in_banners and bool(local_character_portraits),
            },
            outputs={"banners/<style>/<size>_<w>x<h>.png": "Banner images per concept and size (with character compositing if applicable)."},
        )

        self.logger.info(f"Ad banners complete: {len(banners)} images in {os.path.join(self.working_dir, 'banners')}")
        return payload
