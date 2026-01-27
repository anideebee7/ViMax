from typing import List, Optional, Literal, Dict
import asyncio
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from langchain.chat_models.base import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from interfaces import CharacterInScene, ShotDescription, ShotBriefDescription
from interfaces.entities.prop import PropInScene

from utils.core.retry import after_func



system_prompt_template_design_storyboard = \
"""
[Role]
You are a world-class, elite storyboard artist for top-tier film studios. You are a "Visual Architect" who translates words into breathtaking, iconic cinematic frames. You understand composition, lighting, and camera movement as tools for emotional manipulation and visual storytelling.

[Task]
Design a complete storyboard that is a visual masterpiece. Your goal is to achieve a 10/10 score by creating shots that are daring, evocative, and perfectly synchronized with the script's soul.

[Guidelines - The Visual Architecture Standard]
- ICONIC COMPOSITION: Every shot must be "Eye-Candy." Use the rule of thirds, leading lines, framing-within-framing, and extreme perspectives (low-angle hero shots, bird's-eye views) to create a visual feast.
- EMOTIONAL LIGHTING: Describe lighting as a character. Use "Chiaroscuro" (dramatic light and shadow), neon rim lighting, or soft ethereal glows to manipulate the viewer's mood.
- CHARACTER-CENTRIC VIZ: Position characters to reflect their power dynamics and internal states. Use <Alice> in angle brackets for all names.
- CINEMATIC MOTION: Describe "Lens-Based" movement. Push-ins for realization, pans for discovery, and shaky handheld for chaos.
- DIALOGUE SYNC: In `audio_desc`, explicitly state: "CharacterName is speaking: '...'" to ensure mouth-sync.
- SCORE GOAL: Aim for a storyboard that looks like it belongs in a Museum of Modern Art.
"""


human_prompt_template_design_storyboard = \
"""
<SCRIPT>
{script_str}
</SCRIPT>

<CHARACTERS>
{characters_str}
</CHARACTERS>

<USER_REQUIREMENT>
{user_requirement_str}
</USER_REQUIREMENT>
"""



system_prompt_template_decompose_visual_description = \
"""
[Role]
You are an elite cinematic text analyst and visual deconstruction expert. You specialize in breaking down complex visual concepts into the "Trilogy of Motion": The Static Inception, The Kinetic Journey, and The Final Resolution.

[Task]
Deconstruct the shot description into its fundamental cinematic components. Your goal is to provide a breakdown so detailed that a $100M VFX team could build it perfectly.

[Guidelines - The Kinetic Standard]
- FIRST FRAME (Inception): A pure, static snapshot. Describe the "Mise-en-scène" - the arrangement of everything in the frame. Focus on texture, lighting direction, and initial character silhouettes.
- LAST FRAME (Resolution): The final static state. Every movement described in the "Motion" section must be reflected in this final frame's composition.
- MOTION (Kinetic Journey): Describe the "Soul of the Shot." Use precise terms: Dolly Zoom, Vertigo Effect, Crane Shot, Handheld Shake. Describe character movement as "Vector Paths." 
- NO NAMES IN MOTION: Refer to characters by their visual DNA (e.g., "The man in the tattered leather jacket") to ensure the AI generator focuses on the visual rather than the name.
- CONTINUITY INHERITANCE: If a prop or background anchor was established in the First Frame, it MUST be precisely maintained in the Last Frame unless it was the object of the motion.
- SCORE GOAL: Aim for a breakdown that feels like it was written by a master of the craft.
"""


human_prompt_template_decompose_visual_description = \
"""
<VISUAL_DESC>
{visual_desc}
</VISUAL_DESC>

<CHARACTERS>
{characters_str}
</CHARACTERS>
"""


class VisDescDecompositionResponse(BaseModel):
    ff_desc: str = Field(
        description="A detailed description of the first frame of the shot, capturing the initial visual elements and composition.",
        # examples=[
        #     "Medium shot of a supermarket aisle at eye level. Bob(a tall man wearing a blue shirt and jeans) is positioned on the right side of the frame, captured in profile and facing right, while Alice(a young woman with short hair, wearing a green dress) is on the left, shown pushing a shopping cart with her gaze lowered toward the ground. They are arranged in a front-to-back spatial relationship. Shelves line both sides of the frame, and cool-toned fluorescent lighting from above washes over the scene. The vibrant colors of product packaging contrast with the metallic gray of the shopping cart, all contained within a stable, horizontally balanced composition.",
        #     "Extreme long shot. Aerial view from hundreds of meters above the ground. The boundless golden desert resembles undulating frozen waves, occupying the vast majority of the frame. At the very center of the image, a tiny, solitary explorer appears only as a faint dark speck, dragging a long, lonely trail of footprints behind him, stretching all the way to the edge of the frame.",
        #     "Medium shot at eye level angle. Designer A(with a beard, wearing a white suit) leans forward passionately, speaking emphatically. Product Manager B(with a beard, wearing a white T-shirt) sits with crossed arms, looking skeptical. Between them, Development Engineer C(brown hair, wearing a blue T-shirt) appears anxious, glancing between the two. Project Manager D(curly hair, wearing a red T-shirt) prepares to mediate, focusing on a whiteboard. Bright overhead lighting highlights their expressions, with a blurred whiteboard and glass wall in the background.",
        #     "A low-angle close-up shot captures the figure from below, framing him from the chest up. His face appears resolute and commanding, his eyes piercing as he speaks passionately. Flecks of saliva are visible, emphasizing his intensity. The overcast sky breaks with occasional light, casting him as a heroic, almost monumental figure against the gloom.",
        #     "An extremely close-up of an old, motionless pocket watch. Soft light highlights scratches on its brass case and the enamel dial with Roman numerals. The second hand remains fixed at 'VIII', casting a sharp shadow. A wrinkled finger gently touches the glass surface, evoking a tangible sense of stillness and time.",
        #     "An over-the-shoulder shot at eye level, positioned behind Character A(red hair, wearing a white T-shirt). The foreground, including A's shoulder and head, is softly blurred, directing focus onto Character B(with a beard, wearing a white T-shirt)'s face. B's subtle reactions—shifting from surprise to confusion, then to a glimmer of understanding—are clearly visible. The café background is gently blurred with warm lighting.",
        # ]
    )
    ff_vis_char_idxs: List[int] = Field(
        description="A list of indices of characters that are visible in the first frame of the shot, corresponding to the character list provided in the input.",
        examples=[[0], [1], [0, 1], []]
    )
    ff_vis_prop_idxs: List[int] = Field(
        default=[],
        description="A list of indices of props that are visible in the first frame of the shot, corresponding to the prop list provided in the input.",
    )
    lf_desc: str = Field(
        description="A detailed description of the last frame of the shot, capturing the concluding visual elements and composition.",
    )
    lf_vis_char_idxs: List[int] = Field(
        description="A list of indices of characters that are visible in the last frame of the shot, corresponding to the character list provided in the input.",
        examples=[[0], [1], [0, 1], []]
    )
    lf_vis_prop_idxs: List[int] = Field(
        default=[],
        description="A list of indices of props that are visible in the last frame of the shot, corresponding to the prop list provided in the input.",
    )
    motion_desc: str = Field(
        description="The motion description of the shot. Describe the dynamic visual changes within the shot (camera movement and the movement of elements within the frame)",
        examples=[
            "Static camera. Alice (short hair, wearing a green dress) is walking towards the camera.",
            "Dolly in from meidum shot to close-up. Bob (with a beard, wearing a white T-shirt) smiles to the camera.",
        ]
    )
    variation_type: Literal["large", "medium", "small"] = Field(
        description="Indicates the degree of change between the first frame and the last frame.",
    )
    variation_reason: str = Field(
        description="The reason for the variation type of the shot.",
        examples=[
            "This is a smooth transition shot from the sky to the ground. The content of the shot has changed significantly, so the variation type is large.",
            "Compared to the first frame, a new character appears in the last frame, and there are no significant changes in the composition. So the variation type is medium.",
            "Compared to the first frame, there are only minor changes in the composition. So the variation type is small.",
            "This shot only shows Alice speaking and the changes in her facial expressions, thus the variation type is small.",
        ],
    )



system_prompt_template_design_storyboard_default = \
"""
[Role]
You are a world-class, elite storyboard artist for top-tier film studios. You are a "Visual Architect" who translates words into breathtaking, iconic cinematic frames. You understand composition, lighting, and camera movement as tools for emotional manipulation and visual storytelling.

[Task]
Design a complete storyboard that is a visual masterpiece. Your goal is to achieve a 10/10 score by creating shots that are daring, evocative, and perfectly synchronized with the script's soul.

[Guidelines - The Visual Architecture Standard]
- ICONIC COMPOSITION: Every shot must be "Eye-Candy." Use the rule of thirds, leading lines, framing-within-framing, and extreme perspectives (low-angle hero shots, bird's-eye views) to create a visual feast.
- EMOTIONAL LIGHTING: Describe lighting as a character. Use "Chiaroscuro" (dramatic light and shadow), neon rim lighting, or soft ethereal glows to manipulate the viewer's mood.
- CHARACTER-CENTRIC VIZ: Position characters to reflect their power dynamics and internal states. Use <Alice> in angle brackets for all names.
- CINEMATIC MOTION: Describe "Lens-Based" movement. Push-ins for realization, pans for discovery, and shaky handheld for chaos.
- DIALOGUE SYNC: In `audio_desc`, explicitly state: "CharacterName is speaking: '...'" to ensure mouth-sync.
- SCORE GOAL: Aim for a storyboard that looks like it belongs in a Museum of Modern Art.
"""

STORYBOARD_PROFILES = {
    "feature_film": system_prompt_template_design_storyboard_default,
    "short_film": system_prompt_template_design_storyboard_default,
    "tv_series": """
[Role]
You are an elite TV series storyboard artist. You excel at maintaining visual consistency across episodes while ensuring high episodic tension and dynamic character framing.

[Task]
Design a storyboard for a TV series episode. Focus on "Peak TV" aesthetics: cinematic but practical for episodic production.

[Guidelines]
- CONSISTENCY: Ensure recurring sets, character positions, and key props remain consistent.
- VISUAL ANCHORS: Explicitly utilize background visual anchors to maintain location continuity.
- EPISODIC TENSION: Use framing to emphasize power shifts between characters.
- PRODUCTION EFFICIENCY: Focus on a mix of wide master shots and tight emotional close-ups.
- DIALOGUE FOCUS: Prioritize clear visibility of characters during key dialogue exchanges.
""",
    "documentary": """
[Role]
You are a world-renowned documentary cinematographer and storyboard artist. Your style is "Cinematic Verite" - capturing reality with a raw, powerful, and artistic lens.

[Task]
Design a storyboard for a documentary segment. It must feel authentic, visually grounded, and emotionally truthful.

[Guidelines]
- AUTHENTICITY: Avoid "staged" looks. Use handheld-style descriptions, natural lighting, and "found" compositions.
- VISUAL EVIDENCE: Every shot must support the narrative's factual or investigative claims.
- B-ROLL MASTERY: Use evocative B-Roll to represent abstract concepts or historical events.
- INTERVIEW FRAMING: Position subjects with depth and meaningful backgrounds.
""",
    "learning_series": """
[Role]
You are a world-class educational visual producer and lead designer for top-tier online platforms. You are a master of "Pedagogical Visualization" - the art of making complex intellectual concepts instantly clear, engaging, and unforgettable through cinematic visuals.

[Task]
Create a detailed visual plan for an educational episode that is a creative and pedagogical masterpiece. Your goal is a 10/10 score for learning retention, visual clarity, and student obsession.

[Guidelines - The Pedagogical Architecture Standard]
- PEDAGOGICAL CLARITY: Every shot must have a specific learning purpose. Use high-contrast compositions to direct attention to key data.
- INFOGRAPHIC FUSION: Plan every frame to seamlessly integrate text overlays, dynamic diagrams, and highlighted concepts.
- STEP-BY-STEP VIZ: Break complex systems into visceral, logical visual sequences.
- KINETIC ENGAGEMENT: Use "Lens-Based" movement (push-ins for focus, pans for overview) to keep the learner's brain in a state of flow.
- SYMBOLIC COLORS: Use a consistent, professional color DNA to represent different types of information (e.g., blue for theory, green for application).
- SCORE GOAL: Aim for absolute perfection. Your plan should feel like it defines the future of digital learning.
""",
    "podcast": """
[Role]
You are an elite video podcast producer. You specialize in making conversational content visually dynamic and "Obsession-Worthy."

[Task]
Design a storyboard for a video podcast. Focus on multi-cam dynamics and personality-driven framing.

[Guidelines]
- STUDIO DYNAMICS: Use a mix of wide "Studio" shots, medium "Two-Shots," and tight "Reaction" shots.
- MIC-DROP IMPACT: Frame key insights with slow push-ins or dramatic lighting shifts.
- HOST/GUEST CHEMISTRY: Position characters to highlight their interaction and energy.
- VISUAL VARIETY: Use pattern interrupts (graphics, B-roll, or camera angle shifts) every 15-30 seconds.
""",
    "ad": """
[Role]
You are a top-tier commercial storyboard artist for luxury brands and high-conversion games. You are a master of "The 3-Second Hook" and "Visual Desire."

[Task]
Design a high-impact storyboard for an advertisement. Every frame must be designed to stop the scroll and drive action.

[Guidelines - High Conversion]
- STOP THE SCROLL: The first shot must be a visual shock or a breathtaking "Hero" shot.
- LUXURY/PREMIUM AESTHETIC: Use high-contrast lighting, saturated colors, and "Macro" detail shots.
- UI SAFE ZONES (9:16): If vertical, keep brand logos and CTAs in the center safe zone. Avoid bottom and right-side UI overlays of social platforms.
- PRODUCT/BRAND FOCUS: The brand/product must be the "Star" of the frame.
- CALL TO ACTION: The final shots must build relentless momentum towards the purchase/click.
""",
    "music_video": """
[Role]
You are a visionary music video director and storyboard artist. You are known for your "Rhythmic Cinematography" and "Visual Poetry."

[Task]
Design a storyboard that is perfectly synced to the song's soul. It must be iconic, experimental, and visually unforgettable.

[Guidelines - The Visual Poetry Standard]
- RHYTHMIC CUTS: Every camera move and transition must be justified by the music's energy.
- SYMBOLIC IMAGERY: Use abstract visual metaphors to represent the song's lyrics and mood.
- EXPERIMENTAL LIGHTING: Use neon, strobe effects, and extreme color grades to create a unique visual universe.
- PERFORMANCE VS STORY: Balance high-energy "Performance" shots with a compelling "Visual Sub-Plot."
- CHORUS MOTIFS: Identify a "Signature Visual Motif" or "Iconic Move" in the first chorus. You MUST reuse and remix this motif in subsequent choruses to build visual recognition and rhythmic momentum.
- UI SAFE ZONES (9:16): If vertical, keep primary action and faces in the center Golden Zone to avoid TikTok/Reels UI covers.
""",
    "viral_shorts": """
[Role]
You are a master of viral short-form content (TikTok/Reels/Shorts). You understand the "Algorithm of Attention."

[Task]
Design a 15-60 second storyboard for maximum virality. Pacing must be relentless.

[Guidelines - UI Safe Zones]
- THE MICRO-HOOK: The first 0.5 seconds must stop the scroll.
- VERTICAL ARCHITECTURE: Optimize every composition for 9:16 vertical viewing.
- UI SAFE ZONES: Ensure all critical action, character faces, and key text are in the "Golden Center." Avoid the bottom 25% (where captions/music bars are) and the right 15% (where like/comment buttons live).
- PATTERN INTERRUPTS: Change the visual every 1-2 seconds.
- COMMENT-BAIT VIZ: Include subtle, surprising, or controversial details that viewers will want to comment on.
"""
}

class StoryboardArtist(BaseAgent):
    """Storyboard artist that designs shots and decomposes visual descriptions."""
    def __init__(
        self,
        chat_model: BaseChatModel,
        shorts_mode: Optional[Dict] = None,
        pipeline_kind: str = "feature_film"
    ):
        super().__init__(chat_model)
        self.shorts_mode = shorts_mode or {}
        self.pipeline_kind = pipeline_kind if pipeline_kind in STORYBOARD_PROFILES else "feature_film"

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def design_storyboard(
        self,
        script: str,
        characters: List[CharacterInScene],
        props: List[PropInScene] = None,
        visual_anchors: List[str] = None,
        user_requirement: Optional[str] = None,
        retry_timeout: int = 150,
    ) -> List[ShotBriefDescription]:

        class StoryboardResponse(BaseModel):
            storyboard: List[ShotBriefDescription] = Field(
                description="A complete storyboard of the scene, including the visual and audio description of each shot.",
            )

        script_str = script.strip()
        # Build rich character descriptions including role, appearance, and visual features
        char_descriptions = []
        for index, char in enumerate(characters):
            char_line = f"Character {index}: {char.identifier_in_scene}"
            if char.role:
                char_line += f" (role: {char.role})"
            char_line += "\n"
            if char.appearance:
                char_line += f"  Appearance: {char.appearance}\n"
            if char.personality:
                char_line += f"  Personality: {char.personality}\n"
            char_line += f"  Visual Features: {char.static_features}\n"
            if char.dynamic_features and char.dynamic_features != "None":
                char_line += f"  Dynamic Features: {char.dynamic_features}\n"
            char_descriptions.append(char_line)
        characters_str = "\n".join(char_descriptions)

        # Build prop and anchor context
        props_str = "\n".join([p.to_context_block() for p in (props or [])])
        anchors_str = ", ".join(visual_anchors or [])
        context_str = f"KEY PROPS:\n{props_str}\n\nVISUAL ANCHORS: {anchors_str}"

        user_requirement_str = user_requirement.strip() if user_requirement else ""
        user_requirement_str = f"{user_requirement_str}\n\n[CONTINUITY CONTEXT]\n{context_str}"

        parser = PydanticOutputParser(pydantic_object=StoryboardResponse)
        shorts_guidelines = ""
        if self.shorts_mode.get("enabled"):
            max_shots = self.shorts_mode.get("max_shots", 4)
            target_seconds = self.shorts_mode.get("target_duration_seconds", 20)
            min_shot_seconds = self.shorts_mode.get("min_shot_seconds", 4)
            max_shot_seconds = self.shorts_mode.get("max_shot_seconds", 8)
            shorts_guidelines = (
                "\n- Shorts mode is enabled. Optimize for viral YouTube Shorts pacing and vertical framing.\n"
                f"- Use at most {max_shots} shots and ensure the first shot is an immediate visual hook.\n"
                f"- Keep the total duration around {target_seconds} seconds and include `duration_seconds` for each shot.\n"
                f"- Each shot should be {min_shot_seconds}-{max_shot_seconds} seconds with no filler.\n"
                "- Prefer bold composition, high clarity, and fast progression of ideas.\n"
            )
        
        # Select the correct system prompt profile
        system_prompt = STORYBOARD_PROFILES.get(self.pipeline_kind, system_prompt_template_design_storyboard_default)
        
        messages = [
            (
                'system',
                system_prompt.format(
                    format_instructions=parser.get_format_instructions(),
                    shorts_guidelines=shorts_guidelines,
                ) if "{format_instructions}" in system_prompt else f"{system_prompt}\n\n[Output Format]\n{parser.get_format_instructions()}\n{shorts_guidelines}",
            ),
            ('human', human_prompt_template_design_storyboard.format(script_str=script_str, characters_str=characters_str, user_requirement_str=user_requirement_str)),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        parsed = await self.parse_with_repair(response.content, StoryboardResponse)
        return parsed.storyboard




    @retry(stop=stop_after_attempt(3), after=after_func)
    async def decompose_visual_description(
        self,
        shot_brief_desc: ShotBriefDescription,
        characters: List[CharacterInScene],
        props: List[PropInScene] = None,
        retry_timeout: int = 150,
    ) -> ShotDescription:
        parser = PydanticOutputParser(pydantic_object=VisDescDecompositionResponse)
        prompt_template = ChatPromptTemplate.from_messages(
            [
                ('system', system_prompt_template_decompose_visual_description),
                ('human', human_prompt_template_decompose_visual_description),
            ]
        )
        chain = prompt_template | self.chat_model | parser

        visual_desc = shot_brief_desc.visual_desc.strip()

        # Build rich character descriptions for visual decomposition
        char_lines = []
        for char in characters:
            char_line = f"{char.identifier_in_scene}:"
            if char.appearance:
                char_line += f" {char.appearance}."
            char_line += f" (static) {char.static_features}; (dynamic) {char.dynamic_features}"
            char_lines.append(char_line)
        characters_str = "\n".join(char_lines)

        # Build prop context
        props_str = "\n".join([f"Prop {i}: {p.identifier} - {p.description}" for i, p in enumerate(props or [])])

        try:
            decomposition: VisDescDecompositionResponse = await asyncio.wait_for(
                chain.ainvoke(
                    input={
                        "format_instructions": parser.get_format_instructions(),
                        "visual_desc": visual_desc,
                        "characters_str": f"{characters_str}\n\nPROPS:\n{props_str}",
                    },
                ),
                timeout=retry_timeout,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse decomposition for shot {shot_brief_desc.idx}: {e}")
            # Try to repair the response if it's a parsing error
            error_str = str(e).lower()
            if "outputparser" in error_str or "parse" in error_str or "json" in error_str:
                self.logger.info(f"Attempting to repair parsing error for shot {shot_brief_desc.idx}...")
                try:
                    # Get raw response without parser
                    raw_chain = prompt_template | self.chat_model
                    raw_response = await asyncio.wait_for(
                        raw_chain.ainvoke(
                            input={
                                "format_instructions": parser.get_format_instructions(),
                                "visual_desc": visual_desc,
                                "characters_str": f"{characters_str}\n\nPROPS:\n{props_str}",
                            },
                        ),
                        timeout=retry_timeout,
                    )
                    # Extract content from response
                    if hasattr(raw_response, 'content'):
                        content = raw_response.content
                    elif isinstance(raw_response, str):
                        content = raw_response
                    else:
                        content = str(raw_response)
                    
                    # Use BaseAgent repair mechanism
                    decomposition = await self._repair_json(content, VisDescDecompositionResponse)
                    self.logger.info(f"Successfully repaired parsing error for shot {shot_brief_desc.idx}")
                except Exception as repair_error:
                    self.logger.error(f"Repair failed for shot {shot_brief_desc.idx}: {repair_error}")
                    raise
            else:
                raise

        return ShotDescription(
            idx=shot_brief_desc.idx,
            is_last=shot_brief_desc.is_last,
            cam_idx=shot_brief_desc.cam_idx,
            visual_desc=shot_brief_desc.visual_desc,
            variation_type=decomposition.variation_type,
            variation_reason=decomposition.variation_reason,
            ff_desc=decomposition.ff_desc,
            ff_vis_char_idxs=decomposition.ff_vis_char_idxs,
            ff_vis_prop_idxs=decomposition.ff_vis_prop_idxs,
            lf_desc=decomposition.lf_desc,
            lf_vis_char_idxs=decomposition.lf_vis_char_idxs,
            lf_vis_prop_idxs=decomposition.lf_vis_prop_idxs,
            motion_desc=decomposition.motion_desc,
            audio_desc=shot_brief_desc.audio_desc,
            duration_seconds=shot_brief_desc.duration_seconds,
        )
