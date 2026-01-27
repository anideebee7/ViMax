"""
Pipeline reasoning and rationale.

Writes structured reasoning for pipeline phases into a `reasoning/` folder
under each run's working_dir:

- Phase 1 (script/lyrics/concept)
- Director: creative brief, vision, tone, pacing, visual_style
- Cinematographer and picturization: shot design, framing, camera choices,
  how the narrative is translated into visuals
- Song: lyrics, composition, and music direction (where applicable)
"""
import os
from typing import Dict, Any, Optional


def _ensure_reasoning_dir(working_dir: str) -> str:
    reasoning_dir = os.path.join(working_dir, "reasoning")
    os.makedirs(reasoning_dir, exist_ok=True)
    return reasoning_dir


def _format_inputs_outputs(inputs: Optional[Dict[str, Any]], outputs: Optional[Dict[str, str]]) -> list:
    blocks = []
    inputs = inputs or {}
    outputs = outputs or {}
    if inputs:
        blocks.append("### Inputs")
        blocks.append("")
        for k, v in inputs.items():
            val_str = str(v)
            if len(val_str) > 400:
                val_str = val_str[:397] + "..."
            blocks.append(f"- **{k}:** {val_str}")
        blocks.append("")
    if outputs:
        blocks.append("### Artifacts")
        blocks.append("")
        for rel_path, desc in outputs.items():
            blocks.append(f"- `{rel_path}` — {desc}")
        blocks.append("")
    return blocks


def write_director_reasoning(
    working_dir: str,
    pipeline_name: str,
    director_name: str,
    rationale: str,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, str]] = None,
) -> str:
    """
    Write the Director's reasoning: creative brief, vision, tone, pacing, visual_style, key_beats.
    Saved as reasoning/director.md.
    """
    reasoning_dir = _ensure_reasoning_dir(working_dir)
    path = os.path.join(reasoning_dir, "director.md")
    blocks = [
        "# Director reasoning",
        "",
        f"**Pipeline:** {pipeline_name}  ",
        f"**Director (or creative lead):** {director_name}",
        "",
        "---",
        "",
        "## Why the director matters",
        "",
        "The director sets the creative brief: tone, pacing, visual style, key beats, and structure. "
        "This steers the screenwriter, storyboard artist, and cinematographer so the final piece "
        "is coherent and on-vision.",
        "",
        "---",
        "",
        "## Director rationale",
        "",
        rationale or "(No rationale provided.)",
        "",
    ]
    blocks.extend(_format_inputs_outputs(inputs, outputs))
    text = "\n".join(blocks).strip() + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def write_cinematographer_picturization_reasoning(
    working_dir: str,
    pipeline_name: str,
    rationale: str,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, str]] = None,
) -> str:
    """
    Write Cinematographer and picturization reasoning: shot design, framing, camera tree,
    storyboard choices, and how the script/lyrics/concept is translated into visuals.
    Saved as reasoning/cinematographer_picturization.md.
    """
    reasoning_dir = _ensure_reasoning_dir(working_dir)
    path = os.path.join(reasoning_dir, "cinematographer_picturization.md")
    blocks = [
        "# Cinematographer and picturization reasoning",
        "",
        f"**Pipeline:** {pipeline_name}",
        "",
        "---",
        "",
        "## Why cinematography and picturization matter",
        "",
        "Cinematography defines shot design, framing, camera movement, and visual language. "
        "Picturization is how the narrative (script, lyrics, concept) is translated into "
        "concrete images and sequences: what to show, when, and from which angle.",
        "",
        "---",
        "",
        "## Rationale",
        "",
        rationale or "(No rationale provided.)",
        "",
    ]
    blocks.extend(_format_inputs_outputs(inputs, outputs))
    text = "\n".join(blocks).strip() + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def write_song_reasoning(
    working_dir: str,
    pipeline_name: str,
    rationale: str,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, str]] = None,
) -> str:
    """
    Write Song reasoning: lyrics rationale, composition choices, and music direction.
    Saved as reasoning/song.md. Use for lyrics (lyrics) and song (lyrics + composition + music).
    """
    reasoning_dir = _ensure_reasoning_dir(working_dir)
    path = os.path.join(reasoning_dir, "song.md")
    blocks = [
        "# Song reasoning",
        "",
        f"**Pipeline:** {pipeline_name}",
        "",
        "---",
        "",
        "## Why song reasoning matters",
        "",
        "Song reasoning covers: why the lyrics were written this way (theme, structure, rhyme, audience), "
        "how the composition supports them (sections, tempo, key, instrumentation), and the "
        "music direction for production (mood, dynamics, style).",
        "",
        "---",
        "",
        "## Rationale",
        "",
        rationale or "(No rationale provided.)",
        "",
    ]
    blocks.extend(_format_inputs_outputs(inputs, outputs))
    text = "\n".join(blocks).strip() + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def write_phase1_reasoning(
    working_dir: str,
    pipeline_name: str,
    phase_label: str = "Phase 1: Story and script",
    content_type: str = "script",
    rationale: str = "",
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, str]] = None,
    extra: Optional[str] = None,
) -> str:
    """
    Write the rationale for Phase 1 (or equivalent) into working_dir/reasoning/.

    Phase 1 is where story, script, or lyrics are created. This documents:
    - WHY: purpose of the phase and how it fits the pipeline
    - WHERE: which artifacts were produced and their paths
    - RATIONALE: creative drivers, director/context influence, inputs that shaped the output

    Args:
        working_dir: Run's working directory (e.g. .working_dir/shortmovie_video/run_id)
        pipeline_name: e.g. "short_video", "lyrics"
        phase_label: e.g. "Phase 1: Story and script", "Phase 1: Lyrics"
        content_type: "script" | "lyrics" | "ad_script" | "documentary_script" | "concept" | "ideation" | "curriculum" | "input_script"
        rationale: Main rationale behind the script/lyrics/concept
        inputs: Key inputs that drove the output (e.g. premise, director_brief, trend_context)
        outputs: Dict of artifact_rel_path -> brief description
        extra: Optional extra section (e.g. character or format notes)

    Returns:
        Path to the written markdown file.
    """
    reasoning_dir = _ensure_reasoning_dir(working_dir)

    # Normalize phase to a filename: "Phase 1: Story and script" -> "phase1_story_and_script"
    safe_phase = phase_label.lower().replace(" ", "_").replace(":", "").replace("-", "_")
    safe_phase = "".join(c for c in safe_phase if c.isalnum() or c == "_") or "phase1"
    if not safe_phase.startswith("phase"):
        safe_phase = f"phase1_{safe_phase}"
    fname = f"{safe_phase}.md"
    path = os.path.join(reasoning_dir, fname)

    inputs = inputs or {}
    outputs = outputs or {}

    blocks = [
        f"# {phase_label}",
        "",
        f"**Pipeline:** {pipeline_name}  ",
        f"**Content type:** {content_type}",
        "",
        "---",
        "",
        "## Why this phase",
        "",
        "This phase produces the narrative or copy that drives the rest of the pipeline. "
        "The script, lyrics, or concept sets the tone, structure, and creative direction. "
        "Downstream phases (storyboard, visuals, video) rely on this output for consistency and coherence.",
        "",
        "---",
        "",
        "## Rationale behind the script or lyrics",
        "",
        rationale or "(No rationale provided.)",
        "",
        "---",
        "",
        "## Inputs that shaped the output",
        "",
    ]
    for k, v in inputs.items():
        val_str = str(v)
        if len(val_str) > 400:
            val_str = val_str[:397] + "..."
        blocks.append(f"- **{k}:** {val_str}")
        blocks.append("")
    if not inputs:
        blocks.append("- (No structured inputs recorded.)")
        blocks.append("")

    blocks.append("---")
    blocks.append("")
    blocks.append("## Where the artifacts were written")
    blocks.append("")
    for rel_path, desc in outputs.items():
        blocks.append(f"- `{rel_path}` — {desc}")
        blocks.append("")
    if not outputs:
        blocks.append("- (No output paths recorded.)")
        blocks.append("")

    if extra:
        blocks.append("---")
        blocks.append("")
        blocks.append("## Additional notes")
        blocks.append("")
        blocks.append(extra)
        blocks.append("")

    text = "\n".join(blocks).strip() + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
