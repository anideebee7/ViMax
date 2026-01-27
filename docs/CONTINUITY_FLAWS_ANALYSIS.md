# Video Pipeline Continuity Flaws Analysis

## Executive Summary

After analyzing the video generation pipelines (ShortMovieVideoPipeline, MusicVideoPipeline, Script2VideoPipeline), I've identified **critical continuity flaws** in three key areas:

1. **Shot Continuity** - Backgrounds/environments change between shots
2. **Character Continuity** - Characters appear inconsistently across shots  
3. **Object/Prop Continuity** - Props are not visually enforced or tracked

---

## 1. SHOT CONTINUITY FLAWS

### Problem: Background/Environment Inconsistency

**Current Behavior:**
- Each shot generates its background independently
- No reference to previous shots in the same scene
- Background prompts are generated fresh for each shot
- Only `global_reference_images` are used (if provided), not previous shot frames

**Code Evidence:**
```python
# pipelines/movies/short_video.py:698-701
bg_image = await self.image_generator.generate_single_image(
    prompt=bg_prompt,
    reference_image_paths=self._resolve_ref_paths(shot_reference_images[:1]),  # Only global refs!
)
```

**Issues:**
1. **No establishment frame tracking within scenes**: Music video pipeline tracks `location_establishment_frames` but short movie pipeline doesn't
2. **No previous shot reference**: Shot 2 doesn't reference Shot 1's background
3. **Background drift**: Same location appears different across shots
4. **Lighting inconsistency**: Lighting changes between shots in same scene

**Impact:**
- Visual jumps between shots
- Same location looks different
- Breaks spatial continuity
- Unprofessional appearance

---

## 2. CHARACTER CONTINUITY FLAWS

### Problem: Limited View Support & Inconsistent Compositing

**Current Behavior:**
- Only front-view portraits are consistently used
- Side/back views are generated but not always used appropriately
- Character compositing doesn't account for shot angle/viewpoint
- Multiple characters may overlap or position incorrectly

**Code Evidence:**
```python
# pipelines/movies/short_video.py:668-675
# Only uses front view, limits to 2 characters
for char in visible_characters[:2]:  # ⚠️ Only 2 characters max
    char_id = char.identifier_in_scene
    if char_id in character_portraits_registry:
        p_info = character_portraits_registry[char_id].get("front", {})  # ⚠️ Only front view
        p_path = p_info.get("path") if isinstance(p_info, dict) else str(p_info)
```

**Issues:**
1. **View selection not context-aware**: Always uses front view, even for side/back shots
2. **Character limit**: Only 2 characters can be referenced in raw generation
3. **No pose/angle matching**: Front view used even when character should be shown from side
4. **Multi-character positioning**: `composite_multiple_characters` may not handle complex layouts
5. **Scale inconsistency**: Character scale may vary between shots
6. **Character state not tracked**: Clothing, expressions, positions not maintained

**Impact:**
- Characters look wrong from certain angles
- Character positioning conflicts
- Scale mismatches
- Character appearance drifts

---

## 3. OBJECT/PROP CONTINUITY FLAWS

### Problem: Props Generated But Not Enforced

**Current Behavior:**
- Props are extracted and reference images generated
- Prop references are added to `global_reference_images` or mentioned in prompts
- **BUT**: Props are NOT composited into frames like characters
- Props rely entirely on AI prompt interpretation

**Code Evidence:**
```python
# pipelines/music/video.py:654-664
# Props are generated but only added to global references
prop_reference_images.append({
    "path": ref_path,
    "description": f"Visual reference for prop: {prop.identifier}. {prop.description}"
})

# Later in frame generation:
# Props are mentioned in prompts but NOT composited
# Only characters get composited!
```

**Issues:**
1. **No prop compositing**: Props are not overlaid like characters
2. **No prop tracking**: Props' positions/states not tracked across shots
3. **No prop persistence**: If character picks up prop in shot 1, it may not appear in shot 2
4. **Prop state changes**: Props may change appearance (broken, moved, etc.) inconsistently
5. **Prop visibility**: Props may appear/disappear randomly

**Impact:**
- Props look different each time
- Props disappear/reappear inconsistently
- Props don't match reference images
- Breaks narrative continuity

---

## 4. MULTI-CHARACTER CONTINUITY ISSUES

### Problem: Complex Character Interactions Not Handled

**Current Behavior:**
- Multiple characters are detected and composited
- But positioning, relationships, and interactions are not maintained

**Issues:**
1. **Character relationships**: If Character A is left of Character B in shot 1, this may not persist
2. **Character interactions**: Handshakes, conversations, movements not tracked
3. **Character blocking**: Spatial relationships not maintained
4. **Character focus**: Main character vs. background characters not distinguished
5. **Character state**: If Character A is holding something, this may not persist

---

## RECOMMENDED FIXES

### 1. Shot Continuity Fixes

**A. Establishment Frame Tracking Per Scene**
```python
# Track first frame of each scene as establishment frame
scene_establishment_frame = None
for shot in shots:
    if shot == shots[0]:
        # First shot establishes the scene
        scene_establishment_frame = frame_path
    else:
        # Subsequent shots reference establishment frame
        bg_image = await self.image_generator.generate_single_image(
            prompt=bg_prompt,
            reference_image_paths=[scene_establishment_frame, previous_shot_frame],
        )
```

**B. Previous Shot Reference**
```python
# Always reference previous shot's background
previous_shot_bg = None
for shot in shots:
    if previous_shot_bg:
        # Maintain background continuity
        bg_image = await self.image_generator.generate_single_image(
            prompt=bg_prompt,
            reference_image_paths=[previous_shot_bg, establishment_frame],
        )
    previous_shot_bg = frame_path
```

**C. Location-Based Tracking**
```python
# Track backgrounds by location (like music video pipeline does)
location_establishment_frames = {}
for shot in shots:
    location = extract_location_from_shot(shot)
    if location not in location_establishment_frames:
        location_establishment_frames[location] = frame_path
    else:
        # Reference establishment frame for this location
        reference_frames = [location_establishment_frames[location], previous_shot_frame]
```

### 2. Character Continuity Fixes

**A. View-Aware Portrait Selection**
```python
def get_character_portrait_for_shot(character, shot_angle, character_portraits_registry):
    """Select appropriate portrait based on shot angle."""
    if "side" in shot_angle.lower() or "profile" in shot_angle.lower():
        return character_portraits_registry[character].get("side", {}).get("path")
    elif "back" in shot_angle.lower() or "behind" in shot_angle.lower():
        return character_portraits_registry[character].get("back", {}).get("path")
    else:
        return character_portraits_registry[character].get("front", {}).get("path")
```

**B. Character State Tracking**
```python
# Track character state across shots
character_states = {
    "CharacterA": {
        "position": "left",
        "expression": "happy",
        "holding": "sword",
        "clothing": "red shirt"
    }
}

# Use state in prompts and compositing
```

**C. Multi-Character Layout System**
```python
def get_character_layout(visible_characters, frame_desc):
    """Determine spatial layout of multiple characters."""
    # Parse frame description for positions
    # Return ordered list with positions
    return [
        {"character": "A", "position": "left", "scale": 0.4},
        {"character": "B", "position": "right", "scale": 0.35},
    ]
```

### 3. Prop Continuity Fixes

**A. Prop Compositing (Like Characters)**
```python
def _composite_props_on_frame(
    frame_path: str,
    visible_props: List[PropInScene],
    prop_reference_images: Dict[str, str],
    frame_desc: str,
):
    """Composite prop references onto frame for consistency."""
    for prop in visible_props:
        prop_ref_path = prop_reference_images.get(prop.identifier)
        if prop_ref_path and os.path.exists(prop_ref_path):
            position = get_prop_position_from_description(frame_desc, prop.identifier)
            composite_prop_on_image(
                background_path=frame_path,
                prop_path=prop_ref_path,
                output_path=frame_path,
                position=position,
                scale_factor=get_prop_scale_from_context(frame_desc),
            )
```

**B. Prop State Tracking**
```python
# Track prop states across shots
prop_states = {
    "Golden Amulet": {
        "location": "CharacterA's hand",
        "state": "glowing",
        "position": "center-left"
    }
}

# Update state based on script
# Use state in compositing
```

**C. Prop Persistence Logic**
```python
def get_props_for_shot(shot, previous_shot_props, script_context):
    """Determine which props should appear in this shot."""
    # 1. Check if props from previous shot should persist
    # 2. Check if new props are introduced
    # 3. Check if props are removed
    return visible_props
```

### 4. Multi-Character Seamless System

**A. Character Relationship Graph**
```python
class CharacterRelationship:
    """Track relationships between characters."""
    def __init__(self):
        self.spatial_relationships = {}  # "A left of B"
        self.interactions = []  # "A shaking hands with B"
        self.blocking = {}  # Character positions in frame
```

**B. Unified Compositing System**
```python
def composite_all_elements_on_frame(
    frame_path: str,
    characters: List[CharacterInScene],
    props: List[PropInScene],
    background_ref: str,
    layout: CharacterLayout,
):
    """Composite characters, props, and maintain background in one pass."""
    # 1. Generate/load background with reference
    # 2. Composite props first (background layer)
    # 3. Composite characters (foreground layer)
    # 4. Apply lighting/shadow consistency
```

**C. Continuity Memory System**
```python
class ContinuityMemory:
    """Track continuity state across shots."""
    def __init__(self):
        self.character_states = {}
        self.prop_states = {}
        self.background_frames = {}
        self.location_establishments = {}
    
    def update_for_shot(self, shot_num, characters, props, background):
        """Update state after each shot."""
        # Track all changes
        # Store reference frames
        # Maintain relationships
```

---

## IMPLEMENTATION PRIORITY

### High Priority (Critical Flaws)
1. ✅ **Character view selection** - Use side/back views when appropriate (PARTIALLY FIXED)
2. 🔴 **Background establishment frames** - Track and reference per scene
3. 🔴 **Previous shot references** - Reference previous shot's background
4. 🔴 **Prop compositing** - Actually composite props like characters

### Medium Priority (Quality Issues)
5. 🟡 **Character state tracking** - Track positions, expressions, clothing
6. 🟡 **Prop state tracking** - Track prop locations and states
7. 🟡 **Multi-character layout** - Better positioning system

### Low Priority (Enhancements)
8. 🟢 **Character relationship graph** - Track spatial relationships
9. 🟢 **Lighting consistency** - Maintain lighting across shots
10. 🟢 **Continuity memory system** - Unified state tracking

---

## TESTING STRATEGY

1. **Shot Continuity Test**: Generate 3 shots in same location, verify background consistency
2. **Character Continuity Test**: Generate shots with character from different angles, verify character consistency
3. **Prop Continuity Test**: Generate shots where character picks up prop, verify prop appears consistently
4. **Multi-Character Test**: Generate shots with 3+ characters, verify all appear correctly positioned

---

## CONCLUSION

The pipelines have **good character compositing infrastructure** but lack:
- **Background continuity** between shots
- **Prop visual enforcement** (compositing)
- **View-aware character selection**
- **State tracking** across shots

These fixes will significantly improve video quality and professional appearance.
