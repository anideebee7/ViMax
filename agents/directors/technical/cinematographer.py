"""
Cinematographer agent: composes StoryboardArtist and CameraImageGenerator.

Provides a single entry point for shot design, visual decomposition, and camera tree
construction. Used by video pipelines that follow the Director → Screenwriter → Cinematographer flow.

Pipelines can use Cinematographer or continue to use StoryboardArtist and CameraImageGenerator
directly (e.g. Script2VideoPipeline). The underlying tools are the same.
"""

import asyncio
from typing import List, Optional, Dict, Any

from interfaces import (
    CharacterInScene,
    ShotBriefDescription,
    ShotDescription,
    Camera,
    DirectorBrief,
)
from agents.producers.visuals import StoryboardArtist
from agents.producers.visuals import CameraImageGenerator


class Cinematographer:
    """
    Facade over StoryboardArtist and CameraImageGenerator for shot design,
    visual decomposition, and camera-tree construction.
    """

    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        shorts_mode: Optional[Dict[str, Any]] = None,
    ):
        self.storyboard_artist = StoryboardArtist(chat_model=chat_model, shorts_mode=shorts_mode or {})
        self.camera_image_generator = CameraImageGenerator(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
        )

    async def design_storyboard(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: Optional[str] = None,
        director_brief: Optional[DirectorBrief] = None,
        retry_timeout: int = 150,
    ) -> List[ShotBriefDescription]:
        """
        Design a storyboard from script and characters.
        If director_brief is provided, it is appended to user_requirement.
        """
        effective = user_requirement or ""
        if director_brief:
            effective = f"{effective}\n\n{director_brief.to_context_block()}".strip()
        return await self.storyboard_artist.design_storyboard(
            script=script,
            characters=characters,
            user_requirement=effective or None,
            retry_timeout=retry_timeout,
        )

    async def decompose_visual_descriptions(
        self,
        shot_brief_descriptions: List[ShotBriefDescription],
        characters: List[CharacterInScene],
        retry_timeout: int = 120,
    ) -> List[ShotDescription]:
        """Decompose each shot brief into first frame, last frame, and motion."""
        tasks = [
            self.storyboard_artist.decompose_visual_description(
                shot_brief_desc=shot_brief_desc,
                characters=characters,
                retry_timeout=retry_timeout,
            )
            for shot_brief_desc in shot_brief_descriptions
        ]
        return list(await asyncio.gather(*tasks))

    async def construct_camera_tree(
        self,
        shot_descriptions: List[ShotDescription],
    ) -> List[Camera]:
        """Build cameras from shot descriptions and construct the camera tree."""
        cameras: List[Camera] = []
        by_cam: Dict[int, Camera] = {}
        for sd in shot_descriptions:
            if sd.cam_idx not in by_cam:
                c = Camera(idx=sd.cam_idx, active_shot_idxs=[sd.idx])
                cameras.append(c)
                by_cam[sd.cam_idx] = c
            else:
                by_cam[sd.cam_idx].active_shot_idxs.append(sd.idx)
        return await self.camera_image_generator.construct_camera_tree(
            cameras=cameras,
            shot_descs=shot_descriptions,
        )
