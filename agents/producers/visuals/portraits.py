import logging
import os
import asyncio
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from tenacity import retry, stop_after_attempt
from interfaces import CharacterInScene, ImageOutput
from langchain_core.messages import HumanMessage, SystemMessage
from utils.core.retry import after_func



prompt_template_front = \
"""
Generate a full-body, front-view portrait of character {identifier} based on the following description, with a pure white background. The character should be centered in the image, occupying most of the frame. Gazing straight ahead. Standing with arms relaxed at sides. Natural expression.
Features: {features}
Style: {style}
"""

prompt_template_side = \
"""
Generate a full-body, SIDE VIEW portrait of character {identifier} based on the provided front-view portrait, with a pure white background.

CRITICAL REQUIREMENTS:
- This must be the EXACT SAME CHARACTER as the reference image, only shown from a perfect 90-degree side angle (profile view)
- Same design, colors, features, clothing, and all visual elements as the front view
- Character facing left or right, NOT toward the camera
- Full body visible from head to feet
- The character should be centered in the image, occupying most of the frame
- Standing with arms relaxed at sides
- The character must be IDENTICAL to the reference, only the viewing angle changes
"""

prompt_template_back = \
"""
Generate a full-body, BACK VIEW portrait of character {identifier} based on the provided front-view portrait, with a pure white background.

CRITICAL REQUIREMENTS:
- This must be the EXACT SAME CHARACTER as the reference image, only shown from directly behind (180-degree view)
- Same design, colors, features, clothing, and all visual elements as the front view
- Character's back facing the camera
- NO face visible - only the back of the character
- Full body visible from head to feet
- The character should be centered in the image, occupying most of the frame
- The character must be IDENTICAL to the reference, only the viewing angle changes
"""


class CharacterPortraitsGenerator:
    def __init__(
        self,
        image_generator,
    ):
        self.image_generator = image_generator


    @retry(stop=stop_after_attempt(3), after=after_func, reraise=True)
    async def generate_front_portrait(
        self,
        character: CharacterInScene,
        style: str,
        output_dir: Optional[str] = None,
    ) -> ImageOutput:
        features = "(static) " + character.static_features + "; (dynamic) " + character.dynamic_features
        prompt = prompt_template_front.format(
            identifier=character.identifier_in_scene,
            features=features,
            style=style,
        )
        if output_dir:
            debug_dir = os.path.join(output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "front_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)

        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            # size="512x512",
        )
        return image_output

    @retry(stop=stop_after_attempt(3), after=after_func, reraise=True)
    async def generate_side_portrait(
        self,
        character: CharacterInScene,
        front_image_path: str,
        output_dir: Optional[str] = None,
    ) -> ImageOutput:
        prompt = prompt_template_side.format(
            identifier=character.identifier_in_scene,
        )
        if output_dir:
            debug_dir = os.path.join(output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "side_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)

        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=[front_image_path],
            # size="1024x1024",
        )
        return image_output


    @retry(stop=stop_after_attempt(3), after=after_func, reraise=True)
    async def generate_back_portrait(
        self,
        character: CharacterInScene,
        front_image_path: str,
        output_dir: Optional[str] = None,
    ) -> ImageOutput:
        prompt = prompt_template_back.format(
            identifier=character.identifier_in_scene,
        )
        if output_dir:
            debug_dir = os.path.join(output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "back_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)

        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=[front_image_path],
            # size="512x512",
        )
        return image_output