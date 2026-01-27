"""
Podcast Script Parser

Parses podcast scripts into structured scenes, shots, and dialogue
for video generation using ViMax pipelines.
"""
import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class SceneType(str, Enum):
    INTRO = "intro"
    QA = "qa"  # Question & Answer segment
    SONG = "song"
    SKIT = "skit"
    GAME = "game"
    STORY = "story"  # Nana Nova stories
    TECH_BREAK = "tech_break"  # Tinker's inventions
    SILENT_WONDER = "silent_wonder"  # Whispurr segments
    RECAP = "recap"
    OUTRO = "outro"
    TRANSITION = "transition"


@dataclass
class DialogueLine:
    """A single line of dialogue"""
    character: str
    text: str
    stage_direction: Optional[str] = None
    is_song: bool = False
    is_visual_cue: bool = False


@dataclass
class PodcastScene:
    """A scene in the podcast"""
    scene_id: int
    title: str
    scene_type: SceneType
    setting: str
    dialogue: List[DialogueLine] = field(default_factory=list)
    visual_cues: List[str] = field(default_factory=list)
    characters_present: List[str] = field(default_factory=list)
    duration_estimate_seconds: int = 60


@dataclass
class ParsedPodcast:
    """Complete parsed podcast"""
    title: str
    part: int = 1
    scenes: List[PodcastScene] = field(default_factory=list)
    all_characters: List[str] = field(default_factory=list)
    estimated_total_duration: int = 0


class PodcastScriptParser:
    """Parse podcast scripts into structured format for video generation"""
    
    # Character name mappings (script name -> S3 identifier)
    # Maps names as they appear in scripts to S3 folder names
    CHARACTER_MAP = {
        "Autocurio": "autocurio",
        "AUTOcurio": "autocurio",  # Legacy alias
        "DotDot": "DotDot",
        "Gloop": "Gloop",
        "Nana Nova": "NanaNova",
        "NanaNova": "NanaNova",
        "Thinker": "Tinker",  # Script may use "Thinker", S3 has "Tinker"
        "Tinker": "Tinker",
        "Whispurr": "Whispurr",
        # Supporting characters (non-visual)
        "Wind": "Wind",
        "Alarm Clock": "AlarmClock",
        "AlarmClock": "AlarmClock",
        "Dino": "Dino",
        "Kid Voice": "KidVoice",
        "KidVoice": "KidVoice",
    }
    
    # Character priority order (main host first, then co-hosts, then supporting)
    # Uses S3 folder names
    CHARACTER_PRIORITY = [
        "autocurio",   # Main host - always first
        "DotDot",      # Co-host (Flying Drone Assistant)
        "Gloop",       # Co-host (Gelatinous Alien Tourist)
        "NanaNova",    # Storyteller (Wise Elder Human)
        "Tinker",      # Expert (Inventor Kid, Age 10)
        "Whispurr",    # Guide (Cat Guide)
        # Supporting characters (lower priority, often non-visual)
        "Wind",
        "AlarmClock", 
        "Dino",
        "KidVoice",
        "All",
    ]
    
    # Scene type markers
    SCENE_MARKERS = {
        "🗝 Wonder Gate": SceneType.QA,
        "Q&A:": SceneType.QA,
        "🎶 Mini-Song:": SceneType.SONG,
        "🎵 Feature Song": SceneType.SONG,
        "🎵 Big Song": SceneType.SONG,
        "🎵 Finale Song": SceneType.SONG,
        "🎵 Silly Song": SceneType.SONG,
        "🎭 Skit Break": SceneType.SKIT,
        "📚 Skit Break": SceneType.SKIT,
        "🎮 Game Time": SceneType.GAME,
        "🎲 Game Time": SceneType.GAME,
        "🎧 Game Time": SceneType.GAME,
        "🔧 Tinker's Tech Break": SceneType.TECH_BREAK,
        "🧪 Tinker's Tech Break": SceneType.TECH_BREAK,
        "🐱 Whispurr's Silent Wonder": SceneType.SILENT_WONDER,
        "👵 Nana Nova's Story": SceneType.STORY,
        "👵 Nana Nova's Pocket Storylet": SceneType.STORY,
        "🤹 Gloop's Earth Word": SceneType.SKIT,
        "🧠 Rapid Q&A": SceneType.QA,
        "🧩 Recap Round": SceneType.RECAP,
        "💌 Closing Reflection": SceneType.OUTRO,
        "👋 Sign-off": SceneType.OUTRO,
        "🌟 What we learned": SceneType.RECAP,
        "🗺 The Tuning Parade": SceneType.TRANSITION,
        "🐦 The Echo Feather": SceneType.TRANSITION,
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse(self, script_text: str) -> ParsedPodcast:
        """Parse a podcast script into structured format"""
        # Extract title
        title_match = re.search(r'🎙\s*Dear Autocurio[^"]*"([^"]+)"', script_text)
        title = title_match.group(1) if title_match else "Dear Autocurio Episode"
        
        # Check for part number
        part = 2 if "Part 2" in script_text[:1000] else 1
        
        # Split into sections
        sections = self._split_into_sections(script_text)
        
        # Parse each section into scenes
        scenes = []
        all_characters = set()
        scene_id = 0
        
        for section_title, section_content in sections:
            scene = self._parse_section(scene_id, section_title, section_content)
            if scene:
                scenes.append(scene)
                all_characters.update(scene.characters_present)
                scene_id += 1
        
        # Calculate total duration
        total_duration = sum(s.duration_estimate_seconds for s in scenes)
        
        return ParsedPodcast(
            title=title,
            part=part,
            scenes=scenes,
            all_characters=list(all_characters),
            estimated_total_duration=total_duration
        )
    
    def _split_into_sections(self, script_text: str) -> List[Tuple[str, str]]:
        """Split script into major sections"""
        sections = []
        
        # Find all section headers (emoji markers)
        pattern = r'((?:🗝|🎶|🎵|🎭|🎮|🎲|🎧|🔧|🧪|🐱|👵|🤹|🧠|🧩|💌|👋|🌟|🗺|🐦|🫧|💤|⚡|🌙|🧅)[^\n]+)'
        
        parts = re.split(pattern, script_text)
        
        current_title = "Introduction"
        current_content = ""
        
        for i, part in enumerate(parts):
            if any(marker in part for marker in ['🗝', '🎶', '🎵', '🎭', '🎮', '🎲', '🎧', '🔧', '🧪', '🐱', '👵', '🤹', '🧠', '🧩', '💌', '👋', '🌟', '🗺', '🐦', '🫧', '💤', '⚡', '🌙', '🧅']):
                # Save previous section
                if current_content.strip():
                    sections.append((current_title, current_content.strip()))
                current_title = part.strip()
                current_content = ""
            else:
                current_content += part
        
        # Save last section
        if current_content.strip():
            sections.append((current_title, current_content.strip()))
        
        return sections
    
    def _parse_section(self, scene_id: int, title: str, content: str) -> Optional[PodcastScene]:
        """Parse a section into a PodcastScene"""
        # Determine scene type
        scene_type = SceneType.TRANSITION
        for marker, stype in self.SCENE_MARKERS.items():
            if marker in title:
                scene_type = stype
                break
        
        # Extract setting from [Scene: ...] blocks
        setting_match = re.search(r'\[Scene:\s*([^\]]+)\]', content)
        setting = setting_match.group(1) if setting_match else "Studio"
        
        # Extract visual cues
        visual_cues = re.findall(r'\[Visual(?:\s+cue)?:\s*([^\]]+)\]', content)
        
        # Parse dialogue
        dialogue = self._parse_dialogue(content)
        
        # Get characters present (preserving order of first appearance)
        seen_characters = set()
        characters_in_order = []
        for d in dialogue:
            if d.character and d.character not in seen_characters:
                seen_characters.add(d.character)
                characters_in_order.append(d.character)
        
        # Map to S3 identifiers
        characters_mapped = [
            self.CHARACTER_MAP.get(c, c) for c in characters_in_order
        ]
        
        # Sort by character priority (main host first, co-hosts next, etc.)
        def get_priority(char_id: str) -> int:
            try:
                return self.CHARACTER_PRIORITY.index(char_id)
            except ValueError:
                return 999  # Unknown characters go last
        
        characters_present = sorted(set(characters_mapped), key=get_priority)
        
        # Estimate duration based on dialogue length
        word_count = len(content.split())
        duration_estimate = max(30, min(180, word_count // 3))  # ~3 words/second
        
        return PodcastScene(
            scene_id=scene_id,
            title=title.strip(),
            scene_type=scene_type,
            setting=setting,
            dialogue=dialogue,
            visual_cues=visual_cues,
            characters_present=characters_present,
            duration_estimate_seconds=duration_estimate
        )
    
    def _parse_dialogue(self, content: str) -> List[DialogueLine]:
        """Parse dialogue lines from content"""
        dialogue = []
        
        # Pattern for character dialogue: "CharacterName (stage direction):" or "CharacterName:"
        pattern = r'([A-Z][a-zA-Z\s]+?)(?:\s*\(([^)]+)\))?\s*:\s*'
        
        lines = content.split('\n')
        current_char = None
        current_direction = None
        current_text = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this is a new speaker
            match = re.match(pattern, line)
            if match:
                # Save previous dialogue
                if current_char and current_text:
                    is_song = '🎵' in current_text or '🎶' in current_text
                    dialogue.append(DialogueLine(
                        character=current_char,
                        text=current_text.strip(),
                        stage_direction=current_direction,
                        is_song=is_song
                    ))
                
                current_char = match.group(1).strip()
                current_direction = match.group(2)
                current_text = line[match.end():]
            elif line.startswith('[') and line.endswith(']'):
                # Visual cue or stage direction
                dialogue.append(DialogueLine(
                    character="",
                    text=line,
                    is_visual_cue=True
                ))
            elif current_char:
                # Continue previous dialogue
                current_text += " " + line
        
        # Save last dialogue
        if current_char and current_text:
            is_song = '🎵' in current_text or '🎶' in current_text
            dialogue.append(DialogueLine(
                character=current_char,
                text=current_text.strip(),
                stage_direction=current_direction,
                is_song=is_song
            ))
        
        return dialogue
    
    def get_scene_script(self, scene: PodcastScene) -> str:
        """Convert a scene back to script format for video generation"""
        script_parts = []
        
        # Add setting
        script_parts.append(f"[Setting: {scene.setting}]")
        script_parts.append("")
        
        # Add visual cues
        for cue in scene.visual_cues:
            script_parts.append(f"[Visual: {cue}]")
        
        if scene.visual_cues:
            script_parts.append("")
        
        # Add dialogue
        for line in scene.dialogue:
            if line.is_visual_cue:
                script_parts.append(line.text)
            elif line.character:
                if line.stage_direction:
                    script_parts.append(f"{line.character} ({line.stage_direction}): {line.text}")
                else:
                    script_parts.append(f"{line.character}: {line.text}")
        
        return "\n".join(script_parts)
    
    def get_characters_for_scene(self, scene: PodcastScene) -> List[Dict[str, str]]:
        """Get character info for a scene in ViMax format"""
        characters = []
        for i, char_id in enumerate(scene.characters_present):
            # Skip non-character entries
            if char_id in ["KidVoice", "Wind", "AlarmClock", "Dino"]:
                continue
            characters.append({
                "idx": i,
                "identifier_in_scene": char_id,
                "is_visible": True
            })
        return characters
