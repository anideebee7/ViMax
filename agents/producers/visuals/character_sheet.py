"""Character sheet generator for creating unified 3x3 grid character reference images.

This module generates a single character sheet image containing:
- 3 views: Front, Side, Back
- 3 expressions: Neutral, Happy, Sad
- Total: 9 cells in a 3x3 grid

The sheet serves as the canonical reference for character consistency across video pipelines.
"""

import logging
import os
import asyncio
from typing import Optional, Dict, Tuple, List
from PIL import Image

from tenacity import retry, stop_after_attempt

from interfaces import CharacterInScene, ImageOutput
from interfaces.entities.character_sheet import (
    CharacterView,
    CharacterExpression,
    CharacterViewData,
    CharacterViewSet,
    CharacterSheet,
    SHEET_COLUMNS,
    SHEET_ROWS,
    CELL_SIZE,
    SHEET_WIDTH,
    SHEET_HEIGHT,
)
from utils.core.retry import after_func
from utils.media.character_sheet import (
    CharacterSheetSplitter,
    combine_views_to_sheet,
)


logger = logging.getLogger(__name__)


# Prompt templates for different views and expressions
PROMPT_TEMPLATE_SHEET = """
Generate a CHARACTER MODEL SHEET for {identifier} with a pure white background.

This should be a SINGLE IMAGE containing a 3x3 GRID of the SAME CHARACTER shown from different angles and with different expressions:

ROW 1 (Top row - Neutral expression):
- Cell 1: Front view, neutral face
- Cell 2: Side view (profile), neutral face  
- Cell 3: Back view, neutral (no face visible)

ROW 2 (Middle row - Happy expression):
- Cell 1: Front view, happy/smiling face
- Cell 2: Side view (profile), happy/smiling face
- Cell 3: Back view, happy (no face visible)

ROW 3 (Bottom row - Sad expression):
- Cell 1: Front view, sad/frowning face
- Cell 2: Side view (profile), sad/frowning face
- Cell 3: Back view, sad (no face visible)

CRITICAL REQUIREMENTS:
- This is ONE IMAGE with 9 character poses arranged in a 3x3 grid
- ALL 9 CELLS MUST SHOW THE EXACT SAME CHARACTER - only the angle and expression change
- Same design, colors, clothing, features in every cell
- Full body visible in each cell (head to feet)
- Pure white background in each cell
- Each cell should be roughly equal size
- Clear separation between cells (like a model sheet)

CHARACTER DESCRIPTION:
{features}

VISUAL STYLE:
{style}

Output a single 3x3 grid image like a professional character turnaround/model sheet.
"""

PROMPT_TEMPLATE_SINGLE_VIEW = """
Generate a full-body portrait of character {identifier} with a pure white background.

VIEW: {view} view
EXPRESSION: {expression}

REQUIREMENTS:
- Full body visible from head to feet
- Character centered in frame
- Pure white background
- {view_specific_instructions}

CHARACTER FEATURES:
{features}

VISUAL STYLE:
{style}

{reference_instructions}
"""

VIEW_INSTRUCTIONS = {
    CharacterView.FRONT: "Character facing directly toward camera, gazing straight ahead",
    CharacterView.SIDE: "Character in perfect profile view (90-degree side angle), facing left or right, NOT toward camera",
    CharacterView.BACK: "Character facing away from camera (180-degree view), back toward camera, NO face visible",
}

EXPRESSION_INSTRUCTIONS = {
    CharacterExpression.NEUTRAL: "neutral, relaxed facial expression",
    CharacterExpression.HAPPY: "happy, smiling facial expression with visible joy",
    CharacterExpression.SAD: "sad, frowning facial expression showing melancholy",
}


class CharacterSheetGenerator:
    """Generator for creating unified character sheet images.
    
    Can generate either:
    1. A single 3x3 grid sheet image (preferred)
    2. Individual view images that are combined into a sheet
    """
    
    def __init__(self, image_generator):
        """Initialize with an image generator.
        
        Args:
            image_generator: Any image generator with generate_single_image() method
        """
        self.image_generator = image_generator
        self.splitter = CharacterSheetSplitter()
    
    @retry(stop=stop_after_attempt(3), after=after_func, reraise=True)
    async def generate_character_sheet(
        self,
        character: CharacterInScene,
        style: str,
        output_dir: str,
    ) -> Optional[CharacterSheet]:
        """Generate a complete character sheet with all views and expressions.
        
        This method first tries to generate a single 3x3 grid image. If that fails
        or produces poor results, it falls back to generating individual views.
        
        Args:
            character: The character to generate a sheet for
            style: Visual style description
            output_dir: Directory to save the sheet and extracted views
            
        Returns:
            CharacterSheet object with all views, or None on failure
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Build features string
        features = f"(static) {character.static_features}"
        if character.dynamic_features:
            features += f"; (dynamic) {character.dynamic_features}"
        
        # Try to generate a single grid sheet first
        sheet_path = os.path.join(output_dir, "character_sheet.png")
        
        logger.info(f"Generating character sheet for {character.identifier_in_scene}")
        
        # Try single-shot grid generation
        grid_success = await self._try_generate_grid_sheet(
            character, features, style, sheet_path, output_dir
        )
        
        if grid_success and os.path.exists(sheet_path):
            # Validate and split the grid
            is_valid, error = self.splitter.validate_sheet(sheet_path)
            if is_valid:
                logger.info("Grid sheet generated successfully, splitting into views")
                return self.splitter.split_sheet(
                    sheet_path, output_dir, character.identifier_in_scene
                )
            else:
                logger.warning(f"Grid sheet validation failed: {error}, falling back to individual views")
        
        # Fall back to generating individual views
        logger.info("Generating individual views and combining into sheet")
        return await self._generate_individual_views_sheet(
            character, features, style, output_dir
        )
    
    async def _try_generate_grid_sheet(
        self,
        character: CharacterInScene,
        features: str,
        style: str,
        output_path: str,
        output_dir: str,
    ) -> bool:
        """Try to generate a single 3x3 grid sheet image.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            prompt = PROMPT_TEMPLATE_SHEET.format(
                identifier=character.identifier_in_scene,
                features=features,
                style=style,
            )
            
            # Save debug prompt
            debug_dir = os.path.join(output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "sheet_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)
            
            # Generate the sheet (1:1 aspect ratio for 3x3 grid)
            image_output = await self.image_generator.generate_single_image(
                prompt=prompt,
                aspect_ratio="1:1",
            )
            
            # Save the result
            await self._save_image_output(image_output, output_path)
            
            return os.path.exists(output_path)
            
        except Exception as e:
            logger.warning(f"Grid sheet generation failed: {e}")
            return False
    
    async def _generate_individual_views_sheet(
        self,
        character: CharacterInScene,
        features: str,
        style: str,
        output_dir: str,
    ) -> Optional[CharacterSheet]:
        """Generate individual views and combine them into a sheet.
        
        This is the fallback method that generates each view separately.
        """
        views: Dict[Tuple[CharacterView, CharacterExpression], str] = {}
        front_neutral_path: Optional[str] = None
        
        # Generate front neutral first as the reference
        front_neutral_path = await self._generate_single_view(
            character=character,
            features=features,
            style=style,
            view=CharacterView.FRONT,
            expression=CharacterExpression.NEUTRAL,
            output_dir=output_dir,
            reference_path=None,
        )
        
        if not front_neutral_path:
            logger.error("Failed to generate front neutral view")
            return None
        
        views[(CharacterView.FRONT, CharacterExpression.NEUTRAL)] = front_neutral_path
        
        # Generate remaining views using front neutral as reference
        # Create tasks for parallel generation
        tasks = []
        for view in SHEET_COLUMNS:
            for expression in SHEET_ROWS:
                if view == CharacterView.FRONT and expression == CharacterExpression.NEUTRAL:
                    continue  # Already generated
                
                tasks.append(self._generate_single_view(
                    character=character,
                    features=features,
                    style=style,
                    view=view,
                    expression=expression,
                    output_dir=output_dir,
                    reference_path=front_neutral_path,
                ))
        
        # Execute in parallel (with some concurrency limit)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect results
        idx = 0
        for view in SHEET_COLUMNS:
            for expression in SHEET_ROWS:
                if view == CharacterView.FRONT and expression == CharacterExpression.NEUTRAL:
                    continue
                
                result = results[idx]
                idx += 1
                
                if isinstance(result, Exception):
                    logger.warning(f"Failed to generate {view.value}_{expression.value}: {result}")
                elif result:
                    views[(view, expression)] = result
        
        # Combine into sheet
        sheet_path = os.path.join(output_dir, "character_sheet.png")
        combined_path = combine_views_to_sheet(views, sheet_path)
        
        if not combined_path:
            logger.error("Failed to combine views into sheet")
            return None
        
        # Create CharacterSheet from the individual views
        sheet = CharacterSheet(character_id=character.identifier_in_scene)
        sheet.sheet = CharacterViewData(
            path=sheet_path,
            description="Combined character sheet grid (3x3)"
        )
        
        # Build view sets
        for view in CharacterView:
            expressions_dict = {}
            for expression in CharacterExpression:
                path = views.get((view, expression))
                if path:
                    expressions_dict[expression.value] = CharacterViewData(
                        path=path,
                        description=f"{view.value.title()} view, {expression.value} expression"
                    )
            
            if expressions_dict:
                view_set = CharacterViewSet(
                    neutral=expressions_dict.get("neutral"),
                    happy=expressions_dict.get("happy"),
                    sad=expressions_dict.get("sad"),
                )
                setattr(sheet, view.value, view_set)
        
        return sheet
    
    @retry(stop=stop_after_attempt(2), after=after_func, reraise=True)
    async def _generate_single_view(
        self,
        character: CharacterInScene,
        features: str,
        style: str,
        view: CharacterView,
        expression: CharacterExpression,
        output_dir: str,
        reference_path: Optional[str],
    ) -> Optional[str]:
        """Generate a single view image.
        
        Args:
            character: Character to generate
            features: Feature description string
            style: Visual style
            view: Camera angle/view
            expression: Facial expression
            output_dir: Output directory
            reference_path: Path to reference image (front neutral) for consistency
            
        Returns:
            Path to generated image, or None on failure
        """
        output_path = os.path.join(output_dir, f"{view.value}_{expression.value}.png")
        
        # Build reference instructions
        if reference_path:
            reference_instructions = (
                "CRITICAL: Use the provided reference image to maintain EXACT character consistency. "
                "The character must be IDENTICAL - same design, colors, clothing, features. "
                "Only the viewing angle and expression should change."
            )
        else:
            reference_instructions = ""
        
        prompt = PROMPT_TEMPLATE_SINGLE_VIEW.format(
            identifier=character.identifier_in_scene,
            view=view.value,
            expression=expression.value,
            view_specific_instructions=VIEW_INSTRUCTIONS[view],
            features=features,
            style=style,
            reference_instructions=reference_instructions,
        )
        
        # Add expression-specific instruction
        if view != CharacterView.BACK:  # Back view has no visible face
            prompt += f"\nFacial expression: {EXPRESSION_INSTRUCTIONS[expression]}"
        
        # Save debug prompt
        debug_dir = os.path.join(output_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, f"{view.value}_{expression.value}_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(prompt)
        
        # Generate the image
        reference_paths = [reference_path] if reference_path else []
        
        try:
            image_output = await self.image_generator.generate_single_image(
                prompt=prompt,
                reference_image_paths=reference_paths,
                aspect_ratio="1:1",
            )
            
            await self._save_image_output(image_output, output_path)
            
            if os.path.exists(output_path):
                logger.debug(f"Generated {view.value}_{expression.value} view")
                return output_path
            
        except Exception as e:
            logger.warning(f"Failed to generate {view.value}_{expression.value}: {e}")
        
        return None
    
    async def _save_image_output(self, image_output: ImageOutput, output_path: str):
        """Save an ImageOutput to a file."""
        import aiohttp
        import aiofiles
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if image_output.fmt == "url":
            # Download from URL
            async with aiohttp.ClientSession() as session:
                async with session.get(image_output.data) as response:
                    if response.status == 200:
                        async with aiofiles.open(output_path, 'wb') as f:
                            await f.write(await response.read())
                    else:
                        raise RuntimeError(f"Failed to download image: {response.status}")
        elif image_output.fmt == "base64":
            import base64
            async with aiofiles.open(output_path, 'wb') as f:
                await f.write(base64.b64decode(image_output.data))
        elif image_output.fmt == "path":
            import shutil
            shutil.copy(image_output.data, output_path)
        else:
            raise ValueError(f"Unknown image format: {image_output.fmt}")
    
    async def generate_from_existing_front(
        self,
        character: CharacterInScene,
        front_neutral_path: str,
        style: str,
        output_dir: str,
    ) -> Optional[CharacterSheet]:
        """Generate a character sheet starting from an existing front neutral portrait.
        
        This is useful for S3 characters that already have a front.png.
        
        Args:
            character: Character metadata
            front_neutral_path: Path to existing front neutral portrait
            style: Visual style
            output_dir: Output directory
            
        Returns:
            CharacterSheet with all views
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Copy the existing front view to the output
        front_output = os.path.join(output_dir, "front_neutral.png")
        if front_neutral_path != front_output:
            import shutil
            shutil.copy(front_neutral_path, front_output)
        
        features = f"(static) {character.static_features}"
        if character.dynamic_features:
            features += f"; (dynamic) {character.dynamic_features}"
        
        # Build views dict starting with existing front
        views: Dict[Tuple[CharacterView, CharacterExpression], str] = {
            (CharacterView.FRONT, CharacterExpression.NEUTRAL): front_output
        }
        
        # Generate remaining views
        tasks = []
        task_keys = []
        
        for view in SHEET_COLUMNS:
            for expression in SHEET_ROWS:
                if view == CharacterView.FRONT and expression == CharacterExpression.NEUTRAL:
                    continue
                
                task_keys.append((view, expression))
                tasks.append(self._generate_single_view(
                    character=character,
                    features=features,
                    style=style,
                    view=view,
                    expression=expression,
                    output_dir=output_dir,
                    reference_path=front_output,
                ))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for key, result in zip(task_keys, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to generate {key[0].value}_{key[1].value}: {result}")
            elif result:
                views[key] = result
        
        # Combine into sheet
        sheet_path = os.path.join(output_dir, "character_sheet.png")
        combine_views_to_sheet(views, sheet_path)
        
        # Create CharacterSheet
        sheet = CharacterSheet(character_id=character.identifier_in_scene)
        sheet.sheet = CharacterViewData(path=sheet_path, description="Combined character sheet")
        
        for view in CharacterView:
            expressions_dict = {}
            for expression in CharacterExpression:
                path = views.get((view, expression))
                if path:
                    expressions_dict[expression.value] = CharacterViewData(
                        path=path,
                        description=f"{view.value.title()} view, {expression.value} expression"
                    )
            
            if expressions_dict:
                setattr(sheet, view.value, CharacterViewSet(
                    neutral=expressions_dict.get("neutral"),
                    happy=expressions_dict.get("happy"),
                    sad=expressions_dict.get("sad"),
                ))
        
        return sheet
