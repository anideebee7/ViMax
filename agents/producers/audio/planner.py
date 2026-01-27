"""
Audio Planner Agent

Analyzes scripts and determines audio requirements at scene and shot levels,
including dialogue, voice-over, narration, dubbing, background music, and sound effects.
"""
import json
import logging
import os
from typing import List, Optional, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from agents.base import BaseAgent
from interfaces.content.audio_plan import (
    AudioPlan, SceneAudioPlan, ShotAudioPlan, AudioRequirement, AudioType
)
from interfaces.content.scene import Scene
from interfaces.content.shot_description import ShotDescription, ShotBriefDescription
from utils.pipeline.voice_memory import VoiceMemory


class AudioPlanner(BaseAgent):
    """Agent that plans audio requirements for scripts at scene and shot levels"""
    
    def __init__(self, chat_model, pipeline_kind: str = "feature_film"):
        super().__init__(chat_model=chat_model)
        self.pipeline_kind = pipeline_kind
        self.logger = logging.getLogger(__name__)
    
    async def plan_audio_for_scenes(
        self,
        scenes: List[Scene],
        shots_per_scene: Optional[Dict[int, List[ShotDescription]]] = None,
        previous_audio_plan: Optional[AudioPlan] = None,
        style: str = "cinematic",
        audience: Optional[str] = None,
        content_format: str = "live_action",
        characters: Optional[List] = None,  # List of CharacterInScene for voice mapping
    ) -> AudioPlan:
        """
        Plan audio requirements for a list of scenes.
        
        Args:
            scenes: List of Scene objects
            shots_per_scene: Optional dict mapping scene_idx to list of ShotDescription objects
            previous_audio_plan: Optional previous audio plan for continuity
            style: Visual/style guide
            audience: Target audience
            content_format: Content format (live_action, animated, etc.)
        
        Returns:
            AudioPlan with scene and shot-level audio requirements
        """
        self.logger.info(f"Planning audio for {len(scenes)} scenes...")
        
        # Build context from previous plan if available
        continuity_context = ""
        global_voice_mapping = {}
        if previous_audio_plan:
            continuity_context = f"""
Previous Audio Plan Context:
- Background Music Theme: {previous_audio_plan.background_music_theme or 'None'}
- Audio Style Guide: {previous_audio_plan.audio_style_guide or 'None'}
- Global Voice Mapping: {json.dumps(previous_audio_plan.global_voice_mapping or {}, indent=2)}
"""
            global_voice_mapping = previous_audio_plan.global_voice_mapping or {}
        
        # Prepare scene data for analysis
        scenes_data = []
        for scene in scenes:
            scene_data = {
                "idx": scene.idx,
                "script": scene.script,
                "characters": [c.identifier_in_scene for c in scene.characters],
                "environment": scene.environment.slugline,
            }
            if shots_per_scene and scene.idx in shots_per_scene:
                scene_data["shots"] = [
                    {
                        "idx": shot.idx,
                        "visual_desc": shot.visual_desc,
                        "audio_desc": shot.audio_desc,
                        "motion_desc": getattr(shot, 'motion_desc', ''),
                    }
                    for shot in shots_per_scene[scene.idx]
                ]
            scenes_data.append(scene_data)
        
        # Create prompt for audio planning
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert Audio Planner for video production. Your task is to analyze scripts and determine detailed audio requirements at both scene and shot levels.

You need to identify:
1. **Dialogue**: Character speech that needs voice generation with lip-sync
2. **Voice-Over**: Narrator voice-over (off-screen narration)
3. **Dubbing**: Dialogue that needs to be dubbed over existing video
4. **Narration**: Documentary-style narration
5. **Background Music**: Style and timing of background music
6. **Music Segments**: Standalone music segments (montages, transitions, emotional moments)
7. **Songs**: Full songs with lyrics (musical numbers, characters singing, karaoke scenes)
8. **Sound Effects**: Specific sound effects needed
9. **Ambient Sounds**: Environmental audio

IMPORTANT: If the script indicates a musical number, song, montage, or any scene where music is the primary content (not just background), identify it as MUSIC_SEGMENT or SONG. These should be generated as standalone audio tracks that can be inserted into the video timeline.

For each shot, determine:
- What type of audio is needed
- If dialogue/voice-over: the exact text, character, emotion, voice style
- If lip-sync is required (when character is visible and speaking)
- If music/song: lyrics (if any), music style, duration, whether it's a musical number
- Timing within the shot
- Background music style if needed
- Sound effects list

For MUSIC_SEGMENT or SONG:
- Extract lyrics from script if characters are singing
- Determine music style/genre based on scene context
- Estimate duration based on script description
- Mark as musical_number=True if it's a full musical performance

Maintain consistency:
- Use the same voice mapping for the same character across scenes
- Maintain audio continuity (background music transitions, etc.)
- Consider the overall style and audience

Return a complete AudioPlan with scene and shot-level requirements."""),
            ("user", """Analyze the following scenes and create a detailed audio plan.

Pipeline Type: {pipeline_kind}
Style: {style}
Audience: {audience}
Content Format: {content_format}
{continuity_context}

Scenes Data:
{scenes_data}

Previous Global Voice Mapping (use for consistency):
{global_voice_mapping}

Create a comprehensive audio plan that identifies:
1. All dialogue that needs voice generation
2. Voice-over/narration requirements
3. Background music needs at scene and shot levels
4. Music segments (standalone music for montages, transitions, emotional moments)
5. Songs (full musical numbers with lyrics, characters singing)
6. Sound effects requirements
7. Timing and synchronization needs

For dialogue, extract the exact text from the script and identify:
- Which character is speaking
- The emotion/tone
- Whether lip-sync is needed (if character is visible in shot)
- Timing within the shot

For music segments and songs:
- Look for script cues like "[MUSIC]", "[SONG]", "[MUSICAL NUMBER]", "[MONTAGE]", "[CHARACTER SINGS]"
- Extract lyrics if characters are singing
- Determine music style based on scene context (upbeat, emotional, dramatic, etc.)
- Estimate duration based on script description or shot duration
- Mark as musical_number=True if it's a full musical performance with characters

Return the complete AudioPlan in JSON format."""),
        ])
        
        parser = PydanticOutputParser(pydantic_object=AudioPlan)
        
        try:
            chain = prompt | self.chat_model | parser
            audio_plan = await chain.ainvoke({
                "pipeline_kind": self.pipeline_kind,
                "style": style,
                "audience": audience or "general",
                "content_format": content_format,
                "continuity_context": continuity_context,
                "scenes_data": json.dumps(scenes_data, indent=2, ensure_ascii=False),
                "global_voice_mapping": json.dumps(global_voice_mapping, indent=2),
            })
            
            self.logger.info(f"Generated audio plan with {len(audio_plan.scene_plans)} scene plans")
            return audio_plan
        except Exception as e:
            self.logger.error(f"Failed to generate audio plan: {e}")
            # Return a basic plan as fallback
            return self._create_fallback_plan(scenes, shots_per_scene)
    
    async def plan_audio_for_shots(
        self,
        shots: List[ShotDescription],
        scene_script: str,
        characters: List[str],
        previous_plan: Optional[ShotAudioPlan] = None,
    ) -> List[ShotAudioPlan]:
        """
        Plan audio requirements for a list of shots within a scene.
        
        Args:
            shots: List of ShotDescription objects
            scene_script: The script text for the scene
            characters: List of character identifiers in the scene
            previous_plan: Optional previous shot audio plan for continuity
        
        Returns:
            List of ShotAudioPlan objects
        """
        self.logger.info(f"Planning audio for {len(shots)} shots...")
        
        shots_data = [
            {
                "idx": shot.idx,
                "visual_desc": shot.visual_desc,
                "audio_desc": shot.audio_desc,
                "motion_desc": getattr(shot, 'motion_desc', ''),
            }
            for shot in shots
        ]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert Audio Planner. Analyze shots and determine detailed audio requirements including dialogue, voice-over, background music, and sound effects."""),
            ("user", """Analyze these shots and create audio plans:

Scene Script: {scene_script}
Characters: {characters}
Previous Plan: {previous_plan}

Shots:
{shots_data}

For each shot, identify:
- Dialogue text and character (if any)
- Voice-over/narration (if any)
- Background music style
- Sound effects needed
- Timing requirements
- Lip-sync needs

Return a list of ShotAudioPlan objects in JSON format."""),
        ])
        
        parser = PydanticOutputParser(pydantic_object=List[ShotAudioPlan])
        
        try:
            chain = prompt | self.chat_model | parser
            shot_plans = await chain.ainvoke({
                "scene_script": scene_script,
                "characters": ", ".join(characters),
                "previous_plan": json.dumps(previous_plan.model_dump() if previous_plan else {}, indent=2),
                "shots_data": json.dumps(shots_data, indent=2, ensure_ascii=False),
            })
            return shot_plans
        except Exception as e:
            self.logger.error(f"Failed to generate shot audio plans: {e}")
            return []
    
    def _create_fallback_plan(
        self,
        scenes: List[Scene],
        shots_per_scene: Optional[Dict[int, List[ShotDescription]]] = None,
    ) -> AudioPlan:
        """Create a basic fallback audio plan"""
        scene_plans = []
        
        for scene in scenes:
            shot_plans = []
            if shots_per_scene and scene.idx in shots_per_scene:
                for shot in shots_per_scene[scene.idx]:
                    requirements = []
                    if shot.audio_desc:
                        # Try to extract basic audio info from audio_desc
                        if "[Speaker]" in shot.audio_desc or "says:" in shot.visual_desc:
                            requirements.append(AudioRequirement(
                                audio_type=AudioType.DIALOGUE,
                                text=shot.audio_desc,
                                priority="important",
                            ))
                        else:
                            requirements.append(AudioRequirement(
                                audio_type=AudioType.BACKGROUND_MUSIC,
                                background_music_style="matching scene mood",
                                priority="optional",
                            ))
                    
                    shot_plans.append(ShotAudioPlan(
                        shot_idx=shot.idx,
                        requirements=requirements,
                        estimated_duration=shot.duration_seconds,
                    ))
            
            scene_plans.append(SceneAudioPlan(
                scene_idx=scene.idx,
                shot_plans=shot_plans,
                overall_audio_type=AudioType.BACKGROUND_MUSIC,
            ))
        
        return AudioPlan(scene_plans=scene_plans)
    
    def save_audio_plan(self, audio_plan: AudioPlan, output_path: str):
        """Save audio plan to JSON file"""
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(audio_plan.model_dump(), f, indent=2, ensure_ascii=False)
        self.logger.info(f"Saved audio plan to {output_path}")
    
    def load_audio_plan(self, input_path: str) -> Optional[AudioPlan]:
        """Load audio plan from JSON file"""
        if not os.path.exists(input_path):
            return None
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return AudioPlan.model_validate(data)
        except Exception as e:
            self.logger.error(f"Failed to load audio plan: {e}")
            return None
    
    def save_to_memory(self, audio_plan: AudioPlan, memory, key: str = "audio_plan"):
        """Save audio plan to agent memory for cross-episode continuity"""
        try:
            if hasattr(memory, 'save'):
                memory.save(key, audio_plan.model_dump())
                self.logger.info(f"Saved audio plan to memory with key: {key}")
            elif hasattr(memory, 'store'):
                memory.store(key, audio_plan.model_dump())
                self.logger.info(f"Stored audio plan to memory with key: {key}")
        except Exception as e:
            self.logger.warning(f"Failed to save audio plan to memory: {e}")
    
    def load_from_memory(self, memory, key: str = "audio_plan") -> Optional[AudioPlan]:
        """Load audio plan from agent memory"""
        try:
            if hasattr(memory, 'load'):
                data = memory.load(key)
                if data:
                    return AudioPlan.model_validate(data)
            elif hasattr(memory, 'get'):
                data = memory.get(key)
                if data:
                    return AudioPlan.model_validate(data)
        except Exception as e:
            self.logger.warning(f"Failed to load audio plan from memory: {e}")
        return None
