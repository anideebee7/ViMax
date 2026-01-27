# Raw Frame Generation and Character Sheets Usage Status

## Overview

All pipelines must generate `_raw` versions of frames (the "gelled" version where characters are naturally integrated) and use character sheets with proper view/expression selection.

## Status by Pipeline

### ✅ Fully Compliant

1. **MoviePipeline** (`pipelines/movies/standard.py`)
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors
   - ✅ 3-track process: Background → Composite → RAW

2. **ShortMovieVideoPipeline** (`pipelines/movies/short_video.py`)
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors
   - ✅ 3-track process: Background → Composite → RAW

3. **KidsMoviePipeline** (`pipelines/movies/kids.py`)
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors
   - ✅ 3-track process: Background → Composite → RAW

4. **Song2MusicVideoPipeline** (`pipelines/music/song_to_video.py`)
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors
   - ✅ 3-track process: Background → Composite → RAW

5. **Podcast2VideoPipeline** (`pipelines/content/podcast.py`)
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors
   - ✅ 3-track process: Background → Composite → RAW

6. **LearningSeriesPipeline** (`pipelines/series/learning.py`)
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors
   - ✅ 3-track process: Background → Composite → RAW

### ✅ Fixed (2026-01-26)

7. **Script2VideoPipeline** (`pipelines/base/script.py`)
   - ✅ **FIXED**: Frame generation order corrected (was RAW first, now Background → Composite → RAW)
   - ✅ **FIXED**: `_composite_characters_on_frame` now uses view/expression selectors
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors

8. **MusicVideoPipeline** (`pipelines/music/video.py`)
   - ✅ **FIXED**: Added view/expression instructions to raw_prompt
   - ✅ **FIXED**: Raw references now use view/expression-based portrait selection
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors

9. **DocumentaryPipeline** (`pipelines/content/documentary.py`)
   - ✅ **FIXED**: Frame generation order corrected (was RAW first, now Background → Composite → RAW)
   - ✅ **FIXED**: Added view/expression instructions to raw_prompt
   - ✅ **FIXED**: Raw references now use view/expression-based portrait selection
   - ✅ Generates `_raw.png` frames
   - ✅ Uses character sheets with view/expression selectors

10. **AdPipeline** (`pipelines/ads/video.py`)
    - ✅ **FIXED**: Frame generation order corrected (was RAW first, now Background → Composite → RAW)
    - ✅ **FIXED**: `_composite_characters_on_ad` now uses view/expression selectors
    - ✅ **FIXED**: Added view/expression instructions to raw_prompt
    - ✅ **FIXED**: Raw references now use view/expression-based portrait selection
    - ✅ Generates `_raw.png` frames
    - ✅ Uses character sheets with view/expression selectors

## Standard 3-Track Process

All pipelines now follow this pattern:

### TRACK 1: BACKGROUND GENERATION
```python
bg_prompt = f"{description}. EMPTY CINEMATIC ENVIRONMENT ONLY. No characters, no people, no robots, no figures."
bg_output = await self.image_generator.generate_single_image(prompt=bg_prompt, ...)
bg_output.save(output_path)
```

### TRACK 2: COMPOSITE CHARACTERS (S3 Portraits)
```python
# Use view/expression selectors
view = get_character_view_for_shot(description)
expression = get_character_expression_for_shot(description)

# Get portrait with view/expression, fallback to front
portrait_path = get_portrait_with_view_expression(char_id, view, expression, registry)

# Composite onto background
composite_character_on_image(background_path=output_path, character_path=portrait_path, ...)
```

### TRACK 3: RAW GENERATION (Gelled Characters)
```python
raw_output_path = output_path.replace(".png", "_raw.png")

# Build character context
char_context = " Characters in scene: " + "; ".join([f"{char}: {char.static_features}" for char in chars]) + "."

# Add view/expression guidance
view_instruction = f" Camera angle: {view.value} view."
expression_instruction = f" Character expressions: {expression.value}."

raw_prompt = f"{description}.{char_context}{view_instruction}{expression_instruction} High quality animation frame, expressive characters gelled into scene. Blend characters naturally into environment."

# Build raw references: composite + character portraits with view/expression
raw_refs = [output_path]  # Composite frame
for char in visible_chars:
    portrait_path = get_portrait_with_view_expression(char_id, view, expression, registry)
    if portrait_path:
        raw_refs.append(portrait_path)

raw_output = await self.image_generator.generate_single_image(
    prompt=raw_prompt,
    reference_image_paths=raw_refs if len(raw_refs) > 1 else None,
    strength=0.55,  # Blend with composite
)
raw_output.save(raw_output_path)
```

## Character Sheet Usage

All pipelines now:
1. ✅ Use `get_character_view_for_shot()` to infer camera angle
2. ✅ Use `get_character_expression_for_shot()` to infer character emotion
3. ✅ Select portraits from character sheet registry using view/expression
4. ✅ Fallback gracefully: view+expression → view+neutral → front+expression → front+neutral
5. ✅ Include `static_features` in prompts for character context
6. ✅ Include view/expression instructions in raw prompts

## Benefits

1. **Visual Consistency**: Characters look the same across shots
2. **Proper Views**: Side shots use side portraits, not front
3. **Expression Matching**: Happy scenes use happy portraits
4. **Natural Integration**: RAW frames blend characters naturally
5. **Storyboard Accuracy**: Composite frames show exact character designs

---

*Last Updated: 2026-01-26*
