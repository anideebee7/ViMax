"""Video Director: creative brief for short-form and standard videos (video, script2video)."""

from typing import Optional, Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from agents.base import BaseAgent
from interfaces import DirectorBrief
from utils.core.retry import after_func


VIDEO_DIRECTOR_SYSTEM = """
[Role]
You are an expert video director for short-form (TikTok, YouTube Shorts, Reels) and standard narrative videos.
You create clear creative briefs that guide the screenwriter and cinematographer: tone, pacing, key beats, and visual style.

[Task]
Produce a Director's Creative Brief for the given idea or script. The brief will be used by the screenwriter and
storyboard/cinematography team to stay aligned on format, tone, and key moments.

[Output]
{format_instructions}

[Guidelines]
- For short-form: emphasize a scroll-stopping hook, rapid pacing, one clear beat, strong visual payoff.
- For standard video: clear three-beat or act structure, satisfying arc, memorable moments.
- Visual style should be specific enough to guide framing and lighting (e.g., "documentary handheld", "cinematic anamorphic", "bright flatlay").
- Key beats should be 3–7 moments that must land; the writer and DP will build around them.
"""

VIDEO_DIRECTOR_HUMAN = """
<IDEA_OR_SCRIPT>
{idea_or_script}
</IDEA_OR_SCRIPT>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>

<FORMAT>
{format_hint}
</FORMAT>

Create a Director's Creative Brief. Format must be "short_form" for shorts and "video" for standard.
"""


VIDEO_DIRECTOR_PROFILES = {
    "feature_film": VIDEO_DIRECTOR_SYSTEM,
    "short_film": VIDEO_DIRECTOR_SYSTEM,
    "tv_series": """
[Role]
You are a legendary TV series director and showrunner. You excel at maintaining high episodic tension and ensuring that every visual choice advances the seasonal arc.

[Task]
Produce a Director's Creative Brief for a TV series episode.

[Guidelines]
- EPISODIC HOOKS: Focus on "Cold Opens" and "End-of-Act" cliffhangers.
- CHARACTER DEPTH: Prioritize framing that reveals internal conflict.
- CONSISTENCY: Ensure sets and lighting remain consistent across episodes.
""",
    "documentary": """
[Role]
You are a world-renowned documentary filmmaker. Your vision is "Cinematic Truth" - capturing authentic human stories with high production value.

[Task]
Produce a Director's Creative Brief for a documentary segment.

[Guidelines]
- AUTHENTICITY: Demand naturalistic lighting and "Verite" style cinematography.
- EVIDENCE-DRIVEN VIZ: Every visual must support the narrative's investigation or thesis.
- EMOTIONAL RESONANCE: Find the "Soul" of the factual story.
""",
    "learning_series": """
[Role]
You are a world-class educational visual director. You specialize in "Pedagogical Flow" and making intellectual concepts visually visceral.

[Task]
Produce a Director's Creative Brief for an educational episode.

[Guidelines]
- PEDAGOGICAL CLARITY: Every visual choice must serve a learning objective.
- INFOGRAPHIC INTEGRATION: Plan frames to accommodate clear text and data overlays.
- KINETIC BRAIN-FLOW: Use pacing and camera movement to maintain student engagement.
""",
    "podcast": """
[Role]
You are an elite video podcast showrunner. You specialize in "Conversational Visuals" and making talking-head content "Obsession-Worthy."

[Task]
Produce a Director's Creative Brief for a video podcast.

[Guidelines]
- STUDIO DYNAMICS: Define a multi-cam rhythm that highlights host/guest chemistry.
- PATTERN INTERRUPTS: Plan visual shifts every 20-30 seconds to prevent listener drop-off.
- MIC-DROP IMPACT: Use lighting and camera focus to emphasize key insights.
""",
    "ad": """
[Role]
You are a top-tier commercial creative director. You are a master of "Immediate Attention" and "Visual Desire."

[Task]
Produce a Director's Creative Brief for a high-impact advertisement.

[Guidelines]
- THE 3-SECOND HOOK: The visual must stop the scroll instantly.
- BRAND AS PROTAGONIST: Every shot must elevate the product/service.
- CONVERSION-DRIVEN PACING: Build relentless momentum towards the Call to Action.
""",
    "music_video": """
[Role]
You are a visionary music video director. You are known for "Visual Poetry" and "Rhythmic Cinematography."

[Task]
Produce a Director's Creative Brief perfectly synced to a song's rhythm and soul.

[Guidelines]
- RHYTHMIC CUTTING: Pacing must be mathematically aligned with the song's BPM and energy shifts.
- SYMBOLIC IMAGERY: Use experimental and abstract visuals to represent the lyrics.
- ICONIC LOOK: Define a visual DNA that becomes synonymous with the song.
- VISUAL MOTIFS: Identify at least one "Signature Visual Motif" (e.g., a specific camera move, a color splash, or a character gesture) during the first chorus. Force its recurrence and evolution in all subsequent choruses to ensure a "Masterpiece" visual coherence.
"""
}

class VideoDirector(BaseAgent):
    """Director agent for video and script2video pipelines."""

    def __init__(self, chat_model, shorts_mode: Optional[Dict[str, Any]] = None, pipeline_kind: str = "feature_film"):
        super().__init__(chat_model)
        self.shorts_mode = shorts_mode or {}
        self.pipeline_kind = pipeline_kind if pipeline_kind in VIDEO_DIRECTOR_PROFILES else "feature_film"

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def direct(
        self,
        idea_or_script: str,
        user_requirement: str = "",
    ) -> DirectorBrief:
        """
        Produce a director's brief for the video.

        Args:
            idea_or_script: The idea (video) or script (script2video).
            user_requirement: User requirements and constraints.

        Returns:
            DirectorBrief for the screenwriter and cinematographer.
        """
        is_shorts = bool(self.shorts_mode.get("enabled"))
        format_hint = (
            "Short-form (Shorts/Reels/TikTok): hook in first second, 1–3 key beats, max ~60s."
            if is_shorts
            else "Standard video: clear act structure, character moments, satisfying arc."
        )

        parser = PydanticOutputParser(pydantic_object=DirectorBrief)
        
        # Select profile
        system_prompt = VIDEO_DIRECTOR_PROFILES.get(self.pipeline_kind, VIDEO_DIRECTOR_SYSTEM)
        
        messages = [
            SystemMessage(content=system_prompt.format(format_instructions=parser.get_format_instructions()) if "{format_instructions}" in system_prompt else f"{system_prompt}\n\n[Output Format]\n{parser.get_format_instructions()}"),
            HumanMessage(
                content=VIDEO_DIRECTOR_HUMAN.format(
                    idea_or_script=idea_or_script[:4000],
                    user_requirement=user_requirement or "None",
                    format_hint=format_hint,
                )
            ),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, DirectorBrief)
