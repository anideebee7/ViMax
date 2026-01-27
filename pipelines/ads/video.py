"""
Idea to Ad Pipeline

Generates advertisement videos from brand/product information
with A/B variants and monetization recommendations.

Supports S3 entity resolution for brands, games, and characters
with character consistency via post-processing compositing.
"""
import json
import logging
import os
import re
from typing import Optional, Dict, Any, List, Literal

import yaml
import importlib
from langchain.chat_models import init_chat_model

from agents.creative.writing import AdCopywriter
from agents.directors.marketing import AdDirector
from agents.producers.business import MonetizationAdvisor
from agents.planners.strategy import IdeationEngine
from agents.producers.visuals import StoryboardArtist
from agents.producers.analysis.continuity_supervisor import TemporalConsistencyAgent
from utils.core.rate_limiter import RateLimiter
from utils.core.run_id import generate_run_id, write_run_metadata, initialize_run_directory
from utils.pipeline.trend_analyzer import TrendAnalyzer
from utils.pipeline.generator_factory import create_generators_from_config
from utils.pipeline.entity_resolver import resolve_s3_entities
from utils.pipeline.reasoning import write_phase1_reasoning, write_director_reasoning, write_cinematographer_picturization_reasoning
from utils.pipeline.run_memory import RunMemory
from utils.media.image import (
    composite_character_on_image,
    composite_multiple_characters,
    composite_logo_on_image,
    composite_prop_on_image,
    get_character_position_from_description,
    get_character_scale_from_shot_type,
    get_prop_position_from_description,
    get_prop_scale_from_context,
)
from utils.pipeline.continuity import ContinuityMemory
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.entities.character_sheet import CharacterView, CharacterExpression
from utils.pipeline.view_selector import (
    get_character_view_for_shot,
    get_character_expression_for_shot,
)
from interfaces.output.monetization import TrendContext
from interfaces.entities.ideation import IdeationResult
from interfaces.entities.brand_context import BrandContext, GameContext
from interfaces.entities.character import CharacterInScene
from configs.constants.pipeline_profiles import get_pipeline_profile, AD_PROFILE


class AdPipeline:
    """Pipeline to generate advertisement videos from brand/product ideas."""

    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        working_dir: str = ".working_dir/ad",
        trend_analyzer: Optional[TrendAnalyzer] = None,
        force_regenerate: bool = False,
        run_id: Optional[str] = None,
        use_run_id: bool = True,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.trend_analyzer = trend_analyzer
        self.force_regenerate = force_regenerate

        self.base_working_dir = working_dir
        self.working_dir, self.run_id = initialize_run_directory(
            working_dir=working_dir,
            pipeline_name="ad",
            run_id=run_id,
            use_run_id=use_run_id,
        )

        self.ad_copywriter = AdCopywriter(chat_model=self.chat_model, pipeline_kind="ad")
        self.ad_director = AdDirector(chat_model=self.chat_model)
        self.monetization_advisor = MonetizationAdvisor(chat_model=self.chat_model)
        self.ideation_engine = IdeationEngine(chat_model=self.chat_model)
        self.storyboard_artist = StoryboardArtist(chat_model=self.chat_model, pipeline_kind="ad")
        self.continuity_supervisor = TemporalConsistencyAgent(chat_model=self.chat_model)
        self.logger = logging.getLogger(__name__)
        self.memory = RunMemory(pipeline_type="ad", run_id=self.run_id, local_dir=self.working_dir)

    @classmethod
    def init_from_config(cls, config_path: str):
        """Initialize pipeline from YAML config file."""
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), "..", ".."))

        def _resolve_env(value):
            if not isinstance(value, str):
                return value
            if value.startswith("${") and value.endswith("}"):
                return os.getenv(value[2:-1], "")
            if value.startswith("ENV:"):
                return os.getenv(value[4:], "")
            return value

        def _resolve_path(path_value: Optional[str]) -> Optional[str]:
            if not path_value:
                return None
            return path_value if os.path.isabs(path_value) else os.path.join(base_dir, path_value)

        chat_model_args = config["chat_model"]["init_args"]
        chat_model_args = {k: _resolve_env(v) for k, v in chat_model_args.items()}
        chat_model = init_chat_model(**chat_model_args)

        # Rate limiters
        image_rpm = config.get("image_generator", {}).get("max_requests_per_minute")
        video_rpm = config.get("video_generator", {}).get("max_requests_per_minute")

        image_rate_limiter = RateLimiter(max_requests_per_minute=image_rpm) if image_rpm else None
        video_rate_limiter = RateLimiter(max_requests_per_minute=video_rpm) if video_rpm else None

        # Use unified generators with correct fallback chain
        # Image: Gemini -> PiAPI nano-banana-pro -> KieAI nano-banana-pro
        # Video: KieAI veo3_fast -> PiAPI veo3.1 -> Google veo-3.1
        image_generator, video_generator = create_generators_from_config(config)

        # Initialize trend analyzer if configured
        trend_analyzer = None
        if config.get("trend_analyzer"):
            trend_analyzer = TrendAnalyzer.from_config(config["trend_analyzer"])

        return cls(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=_resolve_path(config["working_dir"]) or config["working_dir"],
            trend_analyzer=trend_analyzer,
            force_regenerate=bool(config.get("force_regenerate", False)),
        )

    async def _generate_ad_visual(
        self,
        visual_direction: str,
        brand: str,
        variant_name: str,
        output_path: str,
        director_visual_guidance: Optional[str] = None,
        character_portraits: Optional[Dict[str, Any]] = None,
        characters: Optional[List[CharacterInScene]] = None,
        feature_characters: bool = True,
        logo_path: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a visual frame for the ad with optional character and logo compositing."""
        if not self.image_generator:
            return None

        # Detect characters mentioned in visual direction
        visible_chars = []
        char_refs = []
        if characters and character_portraits:
            for char in characters:
                char_name = char.identifier_in_scene
                if not char_name:
                    continue
                pattern = rf"(?i)\b({re.escape(char_name)}|<{re.escape(char_name)}>)\b"
                if re.search(pattern, visual_direction):
                    visible_chars.append(char)
                    if char_name in character_portraits:
                        front_info = character_portraits[char_name].get("front", {})
                        path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                        if path and os.path.exists(path):
                            char_refs.append(path)

        # Build a prompt for the image generator.
        # We keep character names for context/lighting but avoid detailed physical 
        # descriptions that might cause the AI to render random designs if we're compositing.
        generation_prompt = visual_direction
        if visible_chars:
            char_names = [c.identifier_in_scene for c in visible_chars]
            generation_prompt = f"{generation_prompt}. Featuring: {', '.join(char_names)}."

        prompt = f"Professional advertisement visual for {brand}. {generation_prompt}. Clean, high-quality, commercial grade."
        if director_visual_guidance:
            prompt = f"{prompt} Director guidance: {director_visual_guidance}"
        
        # Stronger instruction to incorporate characters naturally and avoid insertions
        prompt += ". Incorporate characters naturally into the scene. No collages, no picture-in-picture, no separate reference image inserts."
        
        try:
            # LIMIT to top 2 character references to avoid AI generator confusion/inserts
            prioritized_char_refs = []
            if visible_chars and character_portraits:
                # Prioritize characters based on role (main_host first)
                prioritized_chars = sorted(
                    visible_chars, 
                    key=lambda x: 0 if x.role == "main_host" else 1
                )
                for char in prioritized_chars[:2]:
                    char_id = char.identifier_in_scene
                    if char_id in character_portraits:
                        front_info = character_portraits[char_id].get("front", {})
                        path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                        if path and os.path.exists(path):
                            prioritized_char_refs.append(path)

            # TRACK 1: BACKGROUND GENERATION (Clean Environment)
            bg_prompt = prompt
            for char in visible_chars:
                bg_prompt = re.sub(rf"(?i)\b{re.escape(char.identifier_in_scene)}\b", "the center area", bg_prompt)
            bg_prompt += " EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures."
            
            bg_output = await self.image_generator.generate_single_image(
                prompt=bg_prompt,
                reference_image_paths=None,  # Clean background, no character refs
            )
            bg_output.save(output_path)
            
            # TRACK 2: COMPOSITE CHARACTERS & LOGO (for preservation)
            if feature_characters and visible_chars and character_portraits:
                self._composite_characters_on_ad(
                    image_path=output_path,
                    visible_characters=visible_chars,
                    character_portraits=character_portraits,
                    visual_direction=visual_direction,
                )
            
            if logo_path and os.path.exists(logo_path):
                composite_logo_on_image(
                    background_path=output_path,
                    logo_path=logo_path,
                    output_path=output_path,
                    position="top-right",
                    scale_factor=0.15,
                    auto_remove_bg=True
                )
            
            # TRACK 3: RAW GENERATION (Gelled Characters & Brand Assets)
            raw_output_path = output_path.replace(".png", "_raw.png")
            
            # Build character context with static_features
            char_desc_parts = []
            for char in visible_chars:
                if char.static_features:
                    char_desc_parts.append(f"{char.identifier_in_scene}: {char.static_features}")
            char_context = " Characters in scene: " + "; ".join(char_desc_parts) + "." if char_desc_parts else ""
            
            # Add view and expression guidance
            view_instruction = ""
            expression_instruction = ""
            if visible_chars:
                view = get_character_view_for_shot(visual_direction)
                expression = get_character_expression_for_shot(visual_direction)
                view_instruction = f" Camera angle: {view.value} view."
                expression_instruction = f" Character expressions: {expression.value}."
            
            logo_instruction = " with integrated brand logo/icon" if logo_path else ""
            
            raw_prompt = f"""{prompt}.{char_context}{view_instruction}{expression_instruction}{logo_instruction}
High quality animation frame, expressive characters gelled into scene. Blend characters and brand assets naturally into environment. No text, no collages."""
            
            # Build raw references: composite frame + logo + character portraits
            raw_refs = [output_path]  # Start with composite frame
            if logo_path and os.path.exists(logo_path):
                raw_refs.append(logo_path)
                
            if visible_chars and character_portraits:
                for char in visible_chars:
                    char_id = char.identifier_in_scene
                    if char_id in character_portraits:
                        view = get_character_view_for_shot(visual_direction)
                        expression = get_character_expression_for_shot(visual_direction)
                        
                        view_data = character_portraits[char_id].get(view.value, {})
                        char_path = None
                        if isinstance(view_data, dict):
                            expr_data = view_data.get(expression.value, {})
                            char_path = expr_data.get("path") if isinstance(expr_data, dict) else expr_data
                            if not char_path: char_path = view_data.get("path")
                        else: char_path = str(view_data)
                        
                        if not char_path:
                            front_entry = character_portraits[char_id].get("front", {})
                            char_path = front_entry.get("path") if isinstance(front_entry, dict) else str(front_entry)
                        
                        if char_path and os.path.exists(char_path) and char_path not in raw_refs:
                            raw_refs.append(char_path)
            
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, f"{variant_name}_raw_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(raw_prompt)
            
            raw_output = await self.image_generator.generate_single_image(
                prompt=raw_prompt,
                reference_image_paths=raw_refs,
                strength=0.55,  # Blend with composite
            )
            raw_output.save(raw_output_path)
            
            # Return the composite version as the primary (S3 assets preserved "as is")
            # The gelled version exists as _raw.png
            return output_path
        except Exception as e:
            self.logger.warning(f"Failed to generate visual for {variant_name}: {e}")
            return None

    def _composite_characters_on_ad(
        self,
        image_path: str,
        visible_characters: List[CharacterInScene],
        character_portraits: Dict[str, Any],
        visual_direction: str,
    ) -> None:
        """Composite character portraits onto an ad visual using view/expression selectors."""
        if not visible_characters or not os.path.exists(image_path):
            return
        
        # Get view and expression from visual direction
        view = get_character_view_for_shot(visual_direction)
        expression = get_character_expression_for_shot(visual_direction)
        
        portraits_to_composite = []
        for char in visible_characters:
            char_id = char.identifier_in_scene
            if char_id in character_portraits:
                # Try to get view-specific portrait
                view_data = character_portraits[char_id].get(view.value, {})
                if isinstance(view_data, dict):
                    # Try expression-specific path
                    expr_data = view_data.get(expression.value, {})
                    if isinstance(expr_data, dict):
                        path = expr_data.get("path")
                    else:
                        path = expr_data if isinstance(expr_data, str) else None
                    if not path:
                        path = view_data.get("path")
                else:
                    path = str(view_data) if view_data else None
                
                # Fallback to front view
                if not path:
                    front_info = character_portraits[char_id].get("front", {})
                    if isinstance(front_info, dict):
                        path = front_info.get("path")
                    else:
                        path = str(front_info) if front_info else None
                
                if path and os.path.exists(path):
                    portraits_to_composite.append(path)
        
        if not portraits_to_composite:
            return
        
        try:
            if len(portraits_to_composite) == 1:
                position = get_character_position_from_description(visual_direction, visible_characters[0].identifier_in_scene)
                scale = get_character_scale_from_shot_type(visual_direction)
                composite_character_on_image(
                    background_path=image_path,
                    character_path=portraits_to_composite[0],
                    output_path=image_path,
                    position=position,
                    scale_factor=min(scale, 0.45),
                    blend_mode="soft",
                )
            else:
                composite_multiple_characters(
                    background_path=image_path,
                    character_paths=portraits_to_composite[:2],
                    output_path=image_path,
                    scale_factors=[0.35] * min(len(portraits_to_composite), 2),
                )
            self.logger.info(f"Composited {len(portraits_to_composite)} character(s) onto ad visual")
        except Exception as e:
            self.logger.warning(f"Failed to composite characters on ad: {e}")

    async def _generate_ad_video(
        self,
        ad_script: Dict[str, Any],
        variant_name: str,
        first_frame_path: Optional[str],
        output_path: str,
        character_portraits: Optional[Dict[str, Any]] = None,
        characters: Optional[List[CharacterInScene]] = None,
    ) -> Optional[str]:
        """Generate a video for the ad variant with character support."""
        if not self.video_generator:
            return None

        # Build character appearance hints for the prompt
        char_hints = ""
        char_refs = []
        if characters and character_portraits:
            for char in characters[:2]:
                char_name = char.identifier_in_scene
                if char_name and char.static_features:
                    char_hints += f" {char_name}: {char.static_features[:80]}."
                if char_name in character_portraits:
                    front_info = character_portraits[char_name].get("front", {})
                    path = front_info.get("path") if isinstance(front_info, dict) else str(front_info)
                    if path and os.path.exists(path):
                        char_refs.append(path)

        prompt = f"""
Advertisement video for {ad_script.get('brand', 'Brand')}.
Hook: {ad_script.get('hook', '')}
Main message: {ad_script.get('main_message', '')}
Visual direction: {ad_script.get('visual_direction', '')}{char_hints}
Call to action: {ad_script.get('call_to_action', '')}
Style: Professional, engaging, commercial quality.
"""
        try:
            # Combine first frame with character portraits as references
            ref_images = []
            raw_frame_path = first_frame_path.replace(".png", "_raw.png") if first_frame_path else None
            # Use raw frame for video if available, otherwise fallback to composited
            video_ref_frame = raw_frame_path if raw_frame_path and os.path.exists(raw_frame_path) else first_frame_path
            
            if video_ref_frame and os.path.exists(video_ref_frame):
                ref_images.append(video_ref_frame)
            for path in char_refs:
                if len(ref_images) < 4 and path not in ref_images:
                    ref_images.append(path)
            
            video_output = await self.video_generator.generate_single_video(
                prompt=prompt,
                reference_image_paths=ref_images if ref_images else None,
            )
            
            # Save debug prompt
            debug_dir = os.path.join(self.working_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, f"{variant_name}_video_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)
            video_output.save(output_path)
            return output_path
        except Exception as e:
            self.logger.warning(f"Failed to generate video for {variant_name}: {e}")
            return None

    async def __call__(
        self,
        brand: Optional[str] = None,
        product: Optional[str] = None,
        campaign_goal: Optional[str] = None,
        audience: Optional[str] = None,
        ad_format: str = "30s",
        generate_visuals: bool = True,
        generate_videos: bool = True,
        trendy: bool = False,
        auto_ideate: bool = False,
        ideation_mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "viral",
        brand_id: Optional[str] = None,
        game_id: Optional[str] = None,
        character_ids: Optional[List[str]] = None,
        characters: Optional[List[CharacterInScene]] = None,
        character_portraits_registry: Optional[Dict[str, Any]] = None,
        feature_characters: bool = True,
        restitch_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate advertisement videos from brand/product information.

        Args:
            brand: Brand name (optional if auto_ideate=True)
            product: Product or service being advertised (optional if auto_ideate=True)
            campaign_goal: Campaign objective (awareness, conversion, engagement)
            audience: Target audience description
            ad_format: Ad duration/format (6s, 15s, 30s, 60s)
            generate_visuals: Whether to generate visual frames
            generate_videos: Whether to generate video ads (default True for full pipeline)
            trendy: Whether to incorporate trending topics
            auto_ideate: If True, automatically generate ad concept
            ideation_mode: Mode for auto-ideation
            brand_id: S3 brand ID for brand asset resolution
            game_id: S3 game ID for game asset resolution
            character_ids: S3 character IDs to feature in the ad
            characters: Pre-built CharacterInScene objects
            character_portraits_registry: Pre-built character portrait registry
            feature_characters: Whether to composite characters onto visuals

        Returns:
            Dictionary with ad scripts, visuals, videos, and monetization plan
        """
        ideation_result: Optional[IdeationResult] = None
        output_json_path = os.path.join(self.working_dir, "ad_output.json")

        if os.path.exists(output_json_path) and not self.force_regenerate and not restitch_only:
            with open(output_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Initialize character data
        local_character_portraits: Dict[str, Any] = character_portraits_registry or {}
        local_characters: List[CharacterInScene] = characters or []

        # Resolve S3 entities (brand, game, characters)
        logo_path = None
        if brand_id or game_id or character_ids:
            texts = []
            if brand_id:
                texts.append(f"@brand:{brand_id}")
            if game_id:
                texts.append(f"@game:{game_id}")
            for char_id in (character_ids or []):
                texts.append(f"@character:{char_id}")
            
            if texts:
                resolution = resolve_s3_entities(
                    texts=texts,
                    brand_hint=brand_id,
                    game_hint=game_id,
                    working_dir=self.working_dir,
                )
                
                # Extract brand name if resolved
                if resolution.get("brand_data"):
                    brand = brand or resolution["brand_data"].get("name", brand)
                if resolution.get("game_data"):
                    product = product or resolution["game_data"].get("name", product)
                
                # Logo/icon detection
                for ref in resolution.get("reference_images") or []:
                    p = ref.get("path")
                    d = (ref.get("description") or "").lower()
                    if p and os.path.exists(p):
                        if any(kw in d for kw in ["logo", "icon", "brand asset", "app icon", "game icon"]):
                            logo_path = p
                            if (game_id and "icon" in d) or (brand_id and "logo" in d):
                                break
                
                if not logo_path:
                    icon_p = os.path.join(self.working_dir, "brand_assets", "game_icon.png")
                    logo_p = os.path.join(self.working_dir, "brand_assets", "brand_logo.png")
                    if os.path.exists(icon_p): logo_path = icon_p
                    elif os.path.exists(logo_p): logo_path = logo_p

                # Extract character portraits from S3
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
                                        key = "front" if "front" in view else view.split("_")[0]
                                        char_entry[key] = {"path": p, "description": f"{view} of {char_folder}"}
                                        break
                            
                            if "front" not in char_entry:
                                for f in os.listdir(char_path):
                                    if "front" in f.lower() and f.lower().endswith(('.png', '.jpg', '.jpeg')):
                                        char_entry["front"] = {"path": os.path.join(char_path, f), "description": f"Front portrait of {char_folder}"}
                                        break
                            
                            if "front" not in char_entry:
                                for f in os.listdir(char_path):
                                    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                                        char_entry["front"] = {"path": os.path.join(char_path, f), "description": f"Portrait of {char_folder}"}
                                        break

                            if char_entry:
                                local_character_portraits[char_folder] = char_entry
                                # Create CharacterInScene if not provided
                                if not any(c.identifier_in_scene == char_folder for c in local_characters):
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
        
        if local_character_portraits:
            self.logger.info(f"Characters available for ad: {list(local_character_portraits.keys())}")

        # Fetch trends if trendy flag is set or needed for ideation
        trend_context: Optional[TrendContext] = None
        trend_context_block = ""
        if (trendy or (auto_ideate and ideation_mode in ["trends", "viral"])) and self.trend_analyzer:
            self.logger.info("Fetching real-time trends...")
            trend_context = await self.trend_analyzer.fetch_trends(category="advertising")
            trend_context_block = trend_context.to_context_block()
            with open(os.path.join(self.working_dir, "trends.json"), "w", encoding="utf-8") as f:
                json.dump(trend_context.model_dump(), f, ensure_ascii=False, indent=2)

        # RESUME CHECK: Ideation
        ideation_path = os.path.join(self.working_dir, "ideation.json")
        if auto_ideate and os.path.exists(ideation_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing ideation: {ideation_path}")
            with open(ideation_path, "r", encoding="utf-8") as f:
                ideation_data = json.load(f)
                ideation_result = IdeationResult(**ideation_data)
                brand = ideation_data.get("brand", brand)
                product = ideation_data.get("product", product)
                campaign_goal = ideation_data.get("campaign_goal", campaign_goal)
                audience = ideation_data.get("audience", audience)
        elif auto_ideate:
            self.logger.info(f"🧠 Auto-ideating ad concept in {ideation_mode} mode...")
            # ... (Ideation logic) ...
            if ideation_mode == "brand" and brand:
                resolution = resolve_s3_entities(texts=[brand], brand_hint=brand, working_dir=self.working_dir)
                brand_ctx = resolution.get("brand_context"); game_ctx = resolution.get("game_context")
                if brand_ctx or game_ctx:
                    ideation_result = await self.ideation_engine.ideate_for_brand(content_type="ad", brand_context=brand_ctx, game_context=game_ctx, trend_context=trend_context)
            if not ideation_result:
                ideation_result = await self.ideation_engine.ideate(content_type="ad", mode=ideation_mode, audience=audience, trend_context=trend_context, brand_context=brand_ctx, game_context=game_ctx)
            brand = brand or (brand_ctx.name if brand_ctx else "Featured Brand")
            product = product or ideation_result.title
            campaign_goal = campaign_goal or "engagement"
            audience = audience or ideation_result.target_audience
            
            ideation_output = ideation_result.model_dump()
            ideation_output.update({"brand": brand, "product": product, "campaign_goal": campaign_goal, "audience": audience})
            if brand_ctx: ideation_output["brand_context"] = brand_ctx.model_dump()
            if game_ctx: ideation_output["game_context"] = game_ctx.model_dump()
            with open(ideation_path, "w", encoding="utf-8") as f:
                json.dump(ideation_output, f, ensure_ascii=False, indent=2)

        # RESUME CHECK: Ad Script
        script_path = os.path.join(self.working_dir, "ad_script.json")
        if os.path.exists(script_path) and not self.force_regenerate:
            self.logger.info(f"  Resuming from existing ad script: {script_path}")
            with open(script_path, "r", encoding="utf-8") as f:
                from agents.ad_copywriter import AdScript
                ad_script = AdScript(**json.load(f))
        else:
            # Director & Copywriter
            director_brief = await self.ad_director.direct(brand=brand, product=product, campaign_goal=campaign_goal, audience=audience, ad_format=ad_format, additional_context=trend_context_block if trend_context_block else None)
            ad_context = f"{trend_context_block or ''}\n\n{director_brief.to_context_block()}".strip()
            
            self.logger.info("Generating ad script...")
            profile_context = AD_PROFILE.get_full_context()
            ad_script = await self.ad_copywriter.write_ad_script(brand=brand, product=product, campaign_goal=campaign_goal, audience=audience, ad_format=ad_format, additional_context=ad_context, pipeline_profile=profile_context)
            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(ad_script.model_dump(), f, ensure_ascii=False, indent=2)

        # Phase 1 reasoning: rationale behind the ad script
        write_phase1_reasoning(
            working_dir=self.working_dir,
            pipeline_name="ad",
            phase_label="Phase 1: Ad script",
            content_type="ad_script",
            rationale=(
                "The ad script is built for conversion: hook, main message, visual direction, and CTA. "
                "The AdDirector's creative brief (tone, visual style, key differentiators) and the "
                "AdCopywriter's conversion-focused profile drive the structure. Trends and campaign goal "
                "shape the hook and messaging so the ad stays relevant and on-brief."
            ),
            inputs={
                "brand": brand,
                "product": product,
                "campaign_goal": campaign_goal,
                "audience": audience,
                "ad_format": ad_format,
                "director_guidance": director_brief.to_context_block()[:300] if director_brief else None,
                "trend_context_used": bool(trend_context_block),
            },
            outputs={"ad_script.json": "Ad copy with primary and A/B variants (hook, main_message, visual_direction, CTA)."},
        )

        # Generate visuals for variants
        variant_visuals = {}
        variant_videos = {}
        
        director_visual_guidance = f"{director_brief.visual_style}. {director_brief.additional_guidance or ''}".strip() if director_brief else None

        if generate_visuals:
            self.logger.info("Generating ad visuals...")
            # Primary variant
            primary_visual_path = os.path.join(self.working_dir, "primary_visual.png")
            if (os.path.exists(primary_visual_path) and not self.force_regenerate) or restitch_only:
                if os.path.exists(primary_visual_path):
                    self.logger.info(f"  Resuming from existing primary visual: {primary_visual_path}")
                    variant_visuals["primary"] = primary_visual_path
            else:
                visual = await self._generate_ad_visual(
                    visual_direction=ad_script.primary_variant.visual_description if hasattr(ad_script.primary_variant, 'visual_description') else ad_script.primary_variant.visual_direction,
                    brand=brand, variant_name="primary", output_path=primary_visual_path,
                    director_visual_guidance=director_visual_guidance, character_portraits=local_character_portraits,
                    characters=local_characters, feature_characters=feature_characters,
                    logo_path=logo_path,
                )
                if visual: variant_visuals["primary"] = visual

            # A/B variants
            for i, variant in enumerate(ad_script.ab_variants):
                variant_visual_path = os.path.join(self.working_dir, f"variant_{i}_visual.png")
                if (os.path.exists(variant_visual_path) and not self.force_regenerate) or restitch_only:
                    if os.path.exists(variant_visual_path):
                        variant_visuals[f"variant_{i}"] = variant_visual_path
                else:
                    visual = await self._generate_ad_visual(
                        visual_direction=variant.visual_description if hasattr(variant, 'visual_description') else variant.visual_direction,
                        brand=brand, variant_name=variant.variant_name, output_path=variant_visual_path,
                        director_visual_guidance=director_visual_guidance, character_portraits=local_character_portraits,
                        characters=local_characters, feature_characters=feature_characters,
                        logo_path=logo_path,
                    )
                    if visual: variant_visuals[f"variant_{i}"] = visual

        if generate_videos:
            self.logger.info("Generating ad videos...")
            # Primary video
            primary_video_path = os.path.join(self.working_dir, "primary_video.mp4")
            if (os.path.exists(primary_video_path) and not self.force_regenerate) or restitch_only:
                if os.path.exists(primary_video_path):
                    self.logger.info(f"  Resuming/Restitching from existing primary video: {primary_video_path}")
                    variant_videos["primary"] = primary_video_path
            else:
                video = await self._generate_ad_video(
                    ad_script=ad_script.primary_variant.model_dump(), variant_name="primary",
                    first_frame_path=variant_visuals.get("primary"), output_path=primary_video_path,
                    character_portraits=local_character_portraits, characters=local_characters,
                )
                if video: variant_videos["primary"] = video

            # A/B variant videos
            for i, variant in enumerate(ad_script.ab_variants):
                variant_video_path = os.path.join(self.working_dir, f"variant_{i}_video.mp4")
                if (os.path.exists(variant_video_path) and not self.force_regenerate) or restitch_only:
                    if os.path.exists(variant_video_path):
                        variant_videos[f"variant_{i}"] = variant_video_path
                else:
                    video = await self._generate_ad_video(
                        ad_script=variant.model_dump(), variant_name=variant.variant_name,
                        first_frame_path=variant_visuals.get(f"variant_{i}"), output_path=variant_video_path,
                        character_portraits=local_character_portraits, characters=local_characters,
                    )
                    if video: variant_videos[f"variant_{i}"] = video

        # Cinematographer and picturization reasoning
        write_cinematographer_picturization_reasoning(
            working_dir=self.working_dir,
            pipeline_name="ad",
            rationale=(
                "Picturization: each ad variant has a visual_direction from the AdCopywriter; "
                "AdDirector's visual_style and additional_guidance are passed into the image prompt. "
                "We generate one primary visual and one per A/B variant. The video generator uses "
                "the same script (hook, main_message, visual_direction, CTA) and optional first frame. "
                "Framing is implied by 'professional advertisement' and the director's visual style. "
                "Character consistency: S3 characters (or provided character portraits) are composited "
                "onto visuals using post-processing when feature_characters=True. Characters mentioned "
                "in visual_direction are detected using regex word boundaries for precise matching."
            ),
            inputs={
                "primary_visual_direction": ad_script.primary_variant.visual_direction[:200] if ad_script else None,
                "director_visual_style": director_brief.visual_style[:200] if director_brief else None,
                "generate_visuals": generate_visuals,
                "generate_videos": generate_videos,
                "characters_featured": [c.identifier_in_scene for c in local_characters] if local_characters else [],
                "character_compositing_enabled": feature_characters and bool(local_character_portraits),
            },
            outputs={
                "primary_visual.png": "Primary ad visual (with character compositing if applicable).",
                "variant_*_visual.png": "A/B variant visuals (with character compositing if applicable).",
                "primary_video.mp4": "Primary ad video (if generate_videos).",
                "variant_*_video.mp4": "A/B variant videos (if generate_videos).",
            },
        )

        # Generate monetization/ROI plan
        self.logger.info("Generating monetization plan...")
        monetization_plan = await self.monetization_advisor.advise_for_ad(
            brand=brand,
            product=product,
            campaign_goal=campaign_goal,
            audience=audience,
            ad_format=ad_format,
            trend_context=trend_context_block if trend_context_block else None,
        )

        # Build output payload
        payload = {
            "run_id": self.run_id,
            "brand": brand,
            "product": product,
            "campaign_goal": campaign_goal,
            "audience": audience,
            "ad_format": ad_format,
            "trendy": trendy,
            "auto_ideate": auto_ideate,
            "ideation_mode": ideation_mode if auto_ideate else None,
            "ideation_result": ideation_result.model_dump() if ideation_result else None,
            "ad_script": ad_script.model_dump(),
            "variant_visuals": variant_visuals,
            "variant_videos": variant_videos,
            "monetization_plan": monetization_plan.model_dump(),
            "characters_featured": [c.identifier_in_scene for c in local_characters] if local_characters else [],
            "character_compositing_enabled": feature_characters and bool(local_character_portraits),
        }

        # 12. Final Continuity Audit
        self.logger.info("Performing final continuity audit...")
        try:
            continuity_report = await self.continuity_supervisor.review_continuity(
                script=json.dumps(ad_script.model_dump(), ensure_ascii=False),
                storyboard=list(variant_visuals.values()),
                video_metadata=payload
            )
            payload["continuity_report"] = continuity_report.model_dump()
        except Exception as e:
            self.logger.warning(f"Continuity audit failed: {e}")

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Sync all assets and metadata to S3 memory
        self.logger.info(f"Syncing run state to S3: {self.memory.memory_uri}")
        self.memory.sync_to_s3(exclude_patterns=["*.mp4"])

        return payload
