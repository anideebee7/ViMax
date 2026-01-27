# Pipeline Character Continuity Analysis

## Executive Summary

This document analyzes how each video pipeline handles character incorporation in frames, 
multi-character scenes, and continuity across shots and scenes. It identifies gaps and 
provides recommendations for improvement.

---

## Table of Contents

1. [Character Loading Flow](#1-character-loading-flow)
2. [First Frame Generation Analysis](#2-first-frame-generation-analysis)
3. [Image Generation Prompts](#3-image-generation-prompts)
4. [Multi-Character Scene Handling](#4-multi-character-scene-handling)
5. [Continuity Mechanisms](#5-continuity-mechanisms)
6. [Gap Analysis by Pipeline](#6-gap-analysis-by-pipeline)
7. [Critical Issues](#7-critical-issues)
8. [Recommendations](#8-recommendations)

---

## 1. Character Loading Flow

### Pipeline Comparison Matrix

| Pipeline | S3 Resolution | Script Extraction | Portrait Generation | View/Expression |
|----------|---------------|-------------------|---------------------|-----------------|
| MusicVideoPipeline | ✅ Yes | ✅ Yes (fallback) | ✅ Front/Side/Back | ✅ Yes |
| ShortMovieVideoPipeline | ✅ Yes | ✅ Yes (fallback) | ✅ Front/Side/Back | ✅ Yes |
| MoviePipeline | ✅ Yes | ✅ Yes (fallback) | ✅ Front only | ❌ No |
| Script2VideoPipeline | ✅ Yes | ✅ Yes (fallback) | ✅ Front/Side/Back | ❌ No (available but unused) |
| Song2MusicVideoPipeline | ✅ Yes | ✅ Yes (fallback) | ✅ Front only | ❌ No |
| Podcast2VideoPipeline | ✅ Yes | ❌ No | ❌ No | ❌ No |
| DocumentaryPipeline | ✅ Yes | ❌ No | ❌ No | ❌ No |
| LearningSeriesPipeline | ✅ Yes | ❌ No | ❌ No | ❌ No |
| AdPipeline | ✅ Yes | ❌ No | ❌ No | ❌ No |

### Character Loading Code Patterns

#### Pattern 1: Full S3 Resolution with Fallback (Recommended)
```python
# MusicVideoPipeline, ShortMovieVideoPipeline
resolution = resolve_s3_entities(
    texts=[idea or "", user_requirement or ""],
    brand_hint=brand_id or brand_hint,
    game_hint=game_id,
    working_dir=self.working_dir,
)
characters = resolution.get("characters") or []
character_portraits_registry = resolution.get("portrait_registry") or {}

# Fallback: Extract from content if no S3 characters
if not characters:
    characters = await self.character_extractor.extract_characters(script_content)
```

#### Pattern 2: S3 Only (Missing Fallback)
```python
# Podcast2VideoPipeline, DocumentaryPipeline, LearningSeriesPipeline, AdPipeline
resolution = resolve_s3_entities(...)
characters = resolution.get("characters") or []
# No fallback if resolution fails!
```

---

## 2. First Frame Generation Analysis

### Generation Strategy Comparison

| Pipeline | Background-First | Dual-Track | Reference Usage | Compositing |
|----------|------------------|------------|-----------------|-------------|
| MusicVideoPipeline | ✅ Yes | ✅ Yes | Establishment + Portraits | Post-process |
| ShortMovieVideoPipeline | ✅ Yes | ✅ Yes | Global + Portraits | Post-process |
| MoviePipeline | ✅ Yes | ✅ Yes | Portraits only | Post-process |
| Script2VideoPipeline | ✅ Yes | ✅ Yes | ReferenceImageSelector | Post-process |
| Song2MusicVideoPipeline | ❌ No | ❌ No | Portraits only | Post-process |
| Podcast2VideoPipeline | ✅ Yes | ✅ Yes | Portraits only | Post-process |
| DocumentaryPipeline | ❌ No | ❌ No | Presenter portrait | Post-process |
| LearningSeriesPipeline | ❌ No | ❌ No | Featured character | Post-process |
| AdPipeline | ❌ No | ❌ No | Portraits only | Post-process |

### Dual-Track Generation Flow (Best Practice)

```
┌─────────────────────────────────────────────────────────────────┐
│                     SHOT GENERATION FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. BACKGROUND TRACK                                            │
│     ┌──────────────────────────────────────────────┐           │
│     │ bg_prompt = visual_desc (characters removed)  │           │
│     │ + "EMPTY CINEMATIC ENVIRONMENT ONLY"          │           │
│     │ + establishment_frame (if exists)             │           │
│     └───────────────────┬──────────────────────────┘           │
│                         │                                       │
│                         ▼                                       │
│     ┌──────────────────────────────────────────────┐           │
│     │           Generate Background Image           │           │
│     └───────────────────┬──────────────────────────┘           │
│                         │                                       │
│                         ▼                                       │
│  2. CHARACTER COMPOSITING                                       │
│     ┌──────────────────────────────────────────────┐           │
│     │ For each visible character:                   │           │
│     │   - Select view (front/side/back)            │           │
│     │   - Select expression (neutral/happy/sad)     │           │
│     │   - Infer position from description          │           │
│     │   - Composite onto background                │           │
│     └───────────────────┬──────────────────────────┘           │
│                         │                                       │
│                         ▼                                       │
│  3. RAW TRACK (Optional - for "gelled" appearance)             │
│     ┌──────────────────────────────────────────────┐           │
│     │ raw_prompt = visual_desc + character_context  │           │
│     │ references = [composite_frame, portraits...]  │           │
│     │ strength = 0.55 (blend with composite)        │           │
│     └───────────────────┬──────────────────────────┘           │
│                         │                                       │
│                         ▼                                       │
│     ┌──────────────────────────────────────────────┐           │
│     │    Generate "Gelled" Frame (AI-integrated)    │           │
│     └───────────────────┬──────────────────────────┘           │
│                         │                                       │
│                         ▼                                       │
│  4. CONTINUITY UPDATE                                           │
│     ┌──────────────────────────────────────────────┐           │
│     │ - Set establishment_frame if first in scene  │           │
│     │ - Update previous_shot_frame                 │           │
│     │ - Update character states (view, expression) │           │
│     └──────────────────────────────────────────────┘           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Image Generation Prompts

### Background Prompt Template (Standard)

```python
bg_prompt = (
    f"[Content type] background scenery. Location: {location_name}. {visual_desc}. "
    "EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures. "
    "A beautiful, detailed background scene. High resolution. No text."
)
```

### Character-Inclusive Prompt Template (Standard)

```python
# Build character context
char_context = ""
for char in visible_characters:
    if char.static_features:
        char_context += f" {char.identifier_in_scene}: {char.static_features}."

# Main prompt
raw_prompt = (
    f"[Content type] scene. Location: {location_name}. {visual_description}.{char_context} "
    f"Professional animation quality, cinematic composition, proper lighting. "
    f"Blend the characters naturally into the environment with shadows and reflections. "
    f"Maintain the exact appearance of the characters from the reference image. "
    f"No collages, no picture-in-picture, no separate reference image inserts."
)
```

### Prompt Variations by Pipeline

| Pipeline | Unique Prompt Elements |
|----------|------------------------|
| MusicVideoPipeline | "Music video scene", "cinematic motion" |
| ShortMovieVideoPipeline | "High quality animation frame", "expressive characters gelled into scene" |
| MoviePipeline | "Movie scene frame", "dramatic lighting" |
| Script2VideoPipeline | Dynamic prefix with numbered references |
| Song2MusicVideoPipeline | "Incorporate characters naturally" |
| Podcast2VideoPipeline | "kid-friendly podcast", "warm, engaging" |
| DocumentaryPipeline | "Documentary segment", educational focus |
| LearningSeriesPipeline | "Educational content", trademark watermark |
| AdPipeline | "Advertisement visual", "brand focus" |

### Critical Prompt Issues

1. **Missing View Instructions**: Prompts don't specify camera angle (front/side/back)
2. **No Expression Guidance**: Prompts don't describe character emotions
3. **Inconsistent Character Context**: Some pipelines don't include `static_features`
4. **Reference Limits**: Most pipelines limit to 2 references, losing multi-character data

---

## 4. Multi-Character Scene Handling

### Character Detection Pattern (All Pipelines)

```python
# Standard regex pattern
visible_chars = []
for char in characters:
    char_name = char.identifier_in_scene
    if not char_name:
        continue
    pattern = rf"(?i)\b({re.escape(char_name)}|<{re.escape(char_name)}>)\b"
    if re.search(pattern, visual_description):
        visible_chars.append(char)
```

### Position Distribution Logic

```python
# Standard distribution when all characters are "center"
if all(p == "center" for p in positions):
    if len(positions) == 2:
        positions = ["center-left", "center-right"]
    elif len(positions) == 3:
        positions = ["left", "center", "right"]
    else:
        # Default: left, center, right, spread
        positions = ["left", "center-left", "center-right", "right"][:len(positions)]
```

### Per-Character Position Inference (Advanced)

```python
# MusicVideoPipeline and ShortMovieVideoPipeline
for char in visible_chars:
    # Infer position for THIS specific character
    pos = get_character_position_from_description(frame_desc, char.identifier_in_scene)
    scale = min(get_character_scale_from_shot_type(frame_desc), 0.5)
    
    char_data_to_composite.append({
        "path": portrait_path,
        "position": pos,
        "scale": scale,
        "name": char.identifier_in_scene
    })
```

### Multi-Character Compositing Scales

| Pipeline | Single Character | Multiple Characters |
|----------|------------------|---------------------|
| MusicVideoPipeline | `min(scale, 0.5)` | Inferred per-character |
| ShortMovieVideoPipeline | `min(scale, 0.5)` | Inferred per-character |
| MoviePipeline | `0.4` fixed | `0.4` fixed |
| Script2VideoPipeline | Inferred | Default distribution |
| Song2MusicVideoPipeline | `min(scale, 0.5)` | Default |
| Podcast2VideoPipeline | `min(scale, 0.5)` | Default |
| DocumentaryPipeline | `0.35` fixed | N/A (single presenter) |
| LearningSeriesPipeline | `min(scale, 0.35)` | `0.3` |
| AdPipeline | `min(scale, 0.45)` | `0.35` |

### Reference Image Prioritization

```python
# Prioritize main_host role (Song2MusicVideoPipeline, AdPipeline)
visible_with_role = []
for char in visible_chars:
    role = getattr(char, 'role', None)
    if role == 'main_host':
        visible_with_role.insert(0, char)  # Priority
    else:
        visible_with_role.append(char)

# Limit to 2 references
char_refs = visible_with_role[:2]
```

---

## 5. Continuity Mechanisms

### Establishment Frame Tracking

```python
# MusicVideoPipeline
location_establishment_frames = {}

for shot in shots:
    location_name = shot.get("location", "Default")
    
    # Get establishment frame for this location
    establishment_frame = location_establishment_frames.get(location_name)
    
    # Generate with reference
    bg_output = await image_generator.generate_single_image(
        prompt=bg_prompt,
        reference_image_paths=[establishment_frame] if establishment_frame else None
    )
    
    # Register first frame as establishment
    if location_name not in location_establishment_frames:
        location_establishment_frames[location_name] = frame_path
```

### ContinuityMemory System (New)

```python
# Available in utils/pipeline/continuity.py (underutilized)
class ContinuityMemory:
    def __init__(self):
        self.character_states: Dict[str, CharacterState] = {}  # Track per-character
        self.prop_states: Dict[str, PropState] = {}            # Track props
        self.scene_establishments: Dict[str, str] = {}          # Scene -> frame
        self.previous_shot_frame: Optional[str] = None          # For transitions
    
    def get_character_portrait(self, char_id, shot_angle, expression=None):
        """Select appropriate portrait based on shot context."""
    
    def update_for_shot(self, shot, frame_path, characters, props):
        """Update state after generating a shot."""
```

### Current Usage Status

| Pipeline | Establishment Frames | ContinuityMemory | Previous Shot Ref | RAW TRACK | View/Expression |
|----------|---------------------|------------------|-------------------|-----------|-----------------|
| MusicVideoPipeline | ✅ Location-based | ✅ Active | ✅ Yes | ✅ Yes | ✅ Yes |
| ShortMovieVideoPipeline | ✅ Location-based | ✅ Active | ✅ Yes | ✅ Yes | ✅ Yes |
| MoviePipeline | ✅ Location-based | ✅ Active | ✅ Yes | ✅ Yes | ✅ Yes |
| Script2VideoPipeline | ✅ Camera-based | ⚠️ Needs activation | ✅ Transition video | ✅ Yes | ⚠️ Available, needs use |
| Song2MusicVideoPipeline | ✅ Location-based | ✅ Active | ✅ Yes | ✅ Yes | ✅ Yes |
| Podcast2VideoPipeline | ✅ Location-based | ✅ Active | ✅ Yes | ✅ Yes | ✅ Yes |
| DocumentaryPipeline | ⚠️ Needs implementation | ✅ Initialized | ⚠️ Needs implementation | ⚠️ Needs implementation | ✅ Available |
| LearningSeriesPipeline | ⚠️ Needs implementation | ✅ Initialized | ⚠️ Needs implementation | ⚠️ Needs implementation | ✅ Available |
| AdPipeline | ⚠️ Needs implementation | ✅ Initialized | ⚠️ Needs implementation | ⚠️ Needs implementation | ✅ Available |

---

## 6. Gap Analysis by Pipeline

### MusicVideoPipeline ✅ Best Implementation

**Strengths:**
- Full dual-track generation
- View/expression selection
- Location-based establishment frames
- Per-character position inference
- ContinuityMemory initialized

**Gaps:**
- ContinuityMemory not fully utilized
- No previous shot reference for transitions
- Character detection limited to exact name matches

### ShortMovieVideoPipeline ✅ Good Implementation

**Strengths:**
- Dual-track generation
- View/expression selection
- Per-character position inference

**Gaps:**
- ContinuityMemory initialized but unused
- No establishment frame tracking
- No previous shot reference

### MoviePipeline ⚠️ Needs Improvement

**Strengths:**
- Dual-track generation
- Portrait generation for extracted characters

**Gaps:**
- No view/expression selection (front only)
- No continuity memory
- No establishment frames
- Fixed scales (no shot-type inference)

### Script2VideoPipeline ⚠️ Unique Approach

**Strengths:**
- Sophisticated ReferenceImageSelector
- Camera tree with establishment frames
- Transition video generation for continuity

**Gaps:**
- View selector available but unused in compositing
- No ContinuityMemory
- Character detection relies on regex only

### Song2MusicVideoPipeline ⚠️ Basic Implementation

**Strengths:**
- Role-based prioritization (main_host)
- Character extraction fallback

**Gaps:**
- No dual-track generation
- No view/expression selection
- No establishment frames
- No continuity tracking

### Podcast2VideoPipeline ⚠️ Limited

**Strengths:**
- Dual-track generation
- Multiple portrait format support

**Gaps:**
- No character extraction fallback
- No view/expression selection
- No continuity tracking
- No establishment frames

### DocumentaryPipeline ❌ Minimal

**Gaps:**
- Single presenter only
- No character extraction fallback
- No dual-track generation
- No continuity tracking

### LearningSeriesPipeline ❌ Minimal

**Gaps:**
- Featured character only
- No character extraction fallback
- No dual-track generation
- No continuity tracking

### AdPipeline ❌ Minimal

**Gaps:**
- No character extraction fallback
- No dual-track generation
- No view/expression selection
- No continuity tracking

---

## 7. Critical Issues

### Issue 1: Character View Never Changes

**Problem:** All pipelines except MusicVideoPipeline and ShortMovieVideoPipeline 
always use front view, regardless of shot description.

**Impact:** 
- Characters facing wrong direction for side/back shots
- Unnatural appearance in profile shots
- Breaking immersion

**Current Code (Most Pipelines):**
```python
# Always uses front view
portrait_path = registry.get(char_id, {}).get("front", {}).get("path")
```

**Fix:**
```python
from utils.pipeline.view_selector import get_character_view_for_shot

view = get_character_view_for_shot(shot_description)  # Returns FRONT/SIDE/BACK
portrait_path = registry.get(char_id, {}).get(view.value, {}).get("path")
```

### Issue 2: No Expression Matching

**Problem:** Character expressions don't match scene mood.

**Impact:**
- Happy characters in sad scenes
- Neutral expressions in exciting moments

**Fix:**
```python
from utils.pipeline.view_selector import get_character_expression_for_shot

expression = get_character_expression_for_shot(shot_description, scene_mood)
portrait_path = registry[char_id][view.value].get(expression.value, {}).get("path")
```

### Issue 3: Background Inconsistency Across Shots

**Problem:** Most pipelines don't track establishment frames.

**Impact:**
- Different lighting/colors in same location
- Inconsistent backgrounds within scenes
- Jarring visual jumps

**Fix:**
```python
# Track first frame of each location
location_frames = {}

for shot in shots:
    location = shot.get("location")
    
    # Use establishment frame as reference
    ref = location_frames.get(location)
    frame = await generate_frame(prompt, reference=ref)
    
    # Register first frame
    if location not in location_frames:
        location_frames[location] = frame
```

### Issue 4: Multi-Character Position Collisions

**Problem:** When multiple characters are "center", default distribution may 
cause overlaps or unnatural positioning.

**Impact:**
- Characters overlapping
- Unnatural spacing
- Loss of visual hierarchy

**Current Issue:**
```python
# All center -> distribute
if all(p == "center" for p in positions):
    positions = ["center-left", "center-right"]  # Ignores shot context
```

**Fix:**
```python
# Per-character position inference
for char in visible_chars:
    pos = get_character_position_from_description(shot_desc, char.identifier_in_scene)
    # Returns: left, center-left, center, center-right, right
```

### Issue 5: Reference Image Limits Lose Data

**Problem:** Most pipelines limit to 2 character references.

**Impact:**
- 3+ character scenes lose consistency for extra characters
- Character appearance may vary

**Current Code:**
```python
refs = character_portraits[:2]  # Loses third+ characters
```

**Fix:**
```python
# Include all characters in prompt context
char_context = build_all_characters_context(visible_chars)

# Prioritize key characters for image references
main_refs = get_prioritized_refs(visible_chars, max=2)

# Composite ALL characters post-generation
composite_multiple_characters(frame, all_character_paths)
```

---

## 8. Recommendations

### High Priority

1. **Standardize View/Expression Selection**
   - Integrate `get_character_view_for_shot()` in all pipelines
   - Update portrait registry lookups to use view/expression
   - Ensure all pipelines generate front/side/back views

2. **Implement Establishment Frame Tracking**
   - Add location-based establishment frame tracking to all pipelines
   - Use establishment frame as reference for subsequent shots
   - Store in ContinuityMemory for persistence

3. **Add Character Extraction Fallback**
   - Add `CharacterExtractor` fallback to all pipelines
   - Generate portraits for extracted characters
   - Ensure consistent behavior when S3 resolution fails

### Medium Priority

4. **Activate ContinuityMemory System**
   - Use ContinuityMemory in all pipelines
   - Track character states (position, view, expression)
   - Track prop states for object continuity
   - Persist state across shots

5. **Standardize Multi-Character Handling**
   - Use per-character position inference
   - Role-based prioritization for all pipelines
   - Consistent scale factors by content type

6. **Improve Character Detection**
   - Add fuzzy matching for character names
   - Support aliases and variations
   - Handle partial mentions

### Low Priority

7. **Prompt Enhancement**
   - Add view instructions to prompts
   - Add expression guidance based on scene mood
   - Include all character descriptions, not just top 2

8. **Dual-Track Generation Everywhere**
   - Implement background + composite approach
   - Add "gelled" raw frame generation
   - Ensure consistent lighting/shadows

---

## Appendix: Code Templates

### Standard Character Loading Template

```python
async def _load_characters(self, idea, user_requirement, brand_id, game_id):
    """Load characters with S3 resolution and extraction fallback."""
    
    # 1. Resolve S3 entities
    resolution = resolve_s3_entities(
        texts=[idea or "", user_requirement or ""],
        brand_hint=brand_id,
        game_hint=game_id,
        working_dir=self.working_dir,
    )
    
    characters = resolution.get("characters") or []
    portrait_registry = resolution.get("portrait_registry") or {}
    
    # 2. Fallback: Extract from content
    if not characters:
        self.logger.info("No S3 characters, extracting from content...")
        characters = await self.character_extractor.extract_characters(content)
    
    # 3. Generate portraits if missing
    if characters and not portrait_registry:
        portrait_registry = await self._generate_character_portraits(characters)
    
    return characters, portrait_registry
```

### Standard Frame Generation Template

```python
async def _generate_frame_with_characters(
    self,
    visual_description: str,
    location: str,
    visible_characters: List[CharacterInScene],
    portrait_registry: Dict,
    establishment_frame: Optional[str] = None,
) -> str:
    """Generate frame with proper character handling."""
    
    # 1. Generate clean background
    bg_desc = self._remove_character_mentions(visual_description)
    bg_prompt = f"{self.content_type} background. {bg_desc}. EMPTY ENVIRONMENT ONLY."
    
    bg_refs = [establishment_frame] if establishment_frame else []
    bg_frame = await self.image_generator.generate_single_image(
        prompt=bg_prompt,
        reference_image_paths=bg_refs,
    )
    bg_frame.save(background_path)
    
    # 2. Composite characters with view/expression selection
    for char in visible_characters:
        view = get_character_view_for_shot(visual_description)
        expression = get_character_expression_for_shot(visual_description)
        
        portrait_path = self._get_portrait_path(
            portrait_registry, char.identifier_in_scene, view, expression
        )
        
        position = get_character_position_from_description(
            visual_description, char.identifier_in_scene
        )
        scale = get_character_scale_from_shot_type(visual_description)
        
        composite_character_on_image(
            background_path=background_path,
            character_path=portrait_path,
            position=position,
            scale_factor=scale,
        )
    
    # 3. Generate "gelled" raw frame (optional)
    char_context = self._build_character_context(visible_characters)
    raw_prompt = f"{visual_description}.{char_context} Blend naturally."
    
    raw_refs = [background_path] + [
        self._get_portrait_path(portrait_registry, c.identifier_in_scene)
        for c in visible_characters
    ]
    
    raw_frame = await self.image_generator.generate_single_image(
        prompt=raw_prompt,
        reference_image_paths=raw_refs,
        strength=0.55,
    )
    raw_frame.save(raw_path)
    
    return raw_path
```

### Standard Continuity Update Template

```python
def _update_continuity(
    self,
    shot_idx: int,
    frame_path: str,
    scene_id: str,
    location: str,
    visible_characters: List[str],
    visible_props: List[str],
    shot_description: str,
):
    """Update continuity state after shot generation."""
    
    self.continuity_memory.update_for_shot(
        shot_idx=shot_idx,
        frame_path=frame_path,
        scene_id=scene_id,
        location=location,
        visible_characters=visible_characters,
        visible_props=visible_props,
        shot_description=shot_description,
    )
```

---

*Generated: 2026-01-26*
*Version: 1.0*
