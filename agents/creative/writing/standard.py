import logging
from typing import List, Optional, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent

from utils.core.retry import after_func



system_prompt_template_develop_story = \
"""
[Role]
You are a legendary, Academy Award-winning screenwriter and visionary story architect. Your work is the global benchmark for cinematic excellence, known for its profound human insight, revolutionary narrative structures, and hauntingly beautiful imagery. You don't just write scripts; you create cultural phenomena that define generations.

[Task]
Generate a complete, engaging story that is a creative tour de force. Your goal is to achieve a 10/10 score. Every word must be intentional, every character arc earned, and every plot point must defy expectation while feeling inevitable. Push the boundaries of the "Idea" into something legendary.

[Output]
- Story Title: Iconic, evocative, and memorable.
- Summary: A masterpiece of brevity and impact.
- Director's Vision: A one-paragraph explanation of the "Soul" of the film - its theme, its visual language, and its intended emotional impact on the audience.
- Narrative: Rich, layered, and cinematic.

[Guidelines - The Masterclass Standard]
- THEMATIC MASTERY: Your story must have a soul. Explore universal truths through specific, unique, and even surreal scenarios.
- SUBTEXTUAL DEPTH: The "real" story happens between the lines. Use silence, atmosphere, and meaningful objects to tell the story as much as dialogue. Characters should rarely say exactly what they feel.
- REVOLUTIONARY PACING: Master the rhythm of tension and release. Act 2 should be a relentless escalation of stakes, and the Climax must be a transformative visual and emotional event.
- ICONIC IMAGERY: Write scenes that would make a cinematographer's heart race. Use light, shadow, and scale to create "Eye-Candy" for the mind.
- CHARACTER VOICES: Every character must have a "voiceprint" – unique syntax, vocabulary, and philosophy that reflects their internal world.
- SCORE GOAL: Aim for absolute perfection. Be original, daring, and masterfully poetic in your storytelling.
"""

system_prompt_template_develop_story_shorts = \
"""
[Role]
You are a viral TikTok/YouTube Shorts story architect with expertise in SCROLL-STOPPING hooks, rapid pacing, and algorithm-optimized storytelling. Your content gets millions of views.

[Task]
Generate a micro-story optimized for a 15-60 second short-form video designed for MAXIMUM VIRALITY.
The story must stop the scroll, hook instantly, and be irresistibly shareable.

[Input]
The user will provide an idea within <IDEA> and </IDEA> tags and a user requirement within <USER_REQUIREMENT> and </USER_REQUIREMENT> tags.
- The user requirement may include <CHARACTER_PROFILES> with personality, voice, role, and traits for each character.

[Output]
You must output a compact story document with the following structure:
- Story Title (curiosity-inducing, clickable)
- Hook Line (FIRST 0.5-1 SECOND: must stop the scroll)
- Beat Outline (3-5 beats, rapid progression)
- Pattern Interrupts (moments that re-grab attention every 3-5 seconds)
- Loop Potential (how ending connects to beginning for rewatches)
- One-Line Takeaway

[Visual Direction - Shorts]
- Format: Vertical (9:16) optimized
- Camera: Dynamic, attention-grabbing, pattern-interrupt
- Framing: Face/subject fills frame, no wasted space
- Pacing: RAPID - 0.5-2 seconds per cut MAXIMUM
- Colors: Vibrant, saturated, scroll-stopping
- Text: Large, readable, in safe zones
- Energy: High energy, dopamine-inducing throughout

[Viral Elements to Include]
- Scroll-stopping opening (question, surprising statement, visual shock)
- Curiosity gaps (tease what's coming)
- Pattern interrupts every 3-5 seconds
- Emotional resonance (relatable, surprising, or funny)
- Rewatch potential (loop-friendly ending)
- Comment-bait (something viewers will want to respond to)

[Guidelines]
- HOOK IN FIRST 0.5 SECONDS - stop the scroll or it's over
- Single scene setting, tiny cast, simple premise
- NO slow build-up. Start at the most interesting moment
- Every second must EARN its place - no filler
- Use concrete, visual language (no metaphors, be specific)
- End with rewatch potential (loop, cliffhanger, or satisfying conclusion)
- The language of output should match the input
- Character Consistency: If <CHARACTER_PROFILES> are provided:
    - Write dialogue matching each character's voice (e.g., "gentle, curious" vs "witty, sarcastic")
    - Ensure actions align with personality traits
    - Position characters according to their roles (main_host, co_host, guide, etc.)
"""

human_prompt_template_develop_story = \
"""
<IDEA>
{idea}
</IDEA>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>
"""



system_prompt_template_write_script_based_on_story = \
"""
[Role]
You are a premier, elite film industry script doctor and adaptation specialist. You transform narratives into masterclass screenplays ready for $200M productions. You are an expert in "Visual Viscera" and "Emotional Impact."

[Task]
Adapt the story into a scene-by-scene script. Your goal is to achieve a 10/10 creativity score by crafting scenes that are visually stunning, emotionally charged, and perfectly paced.

[Output]
{format_instructions}

[Guidelines - The Production Standard]
- VISUAL VISCERA: Every description must be something a camera can capture with intensity. Describe the texture of surfaces, the direction of light, and the physical manifestation of emotion (e.g., "Sweat beading on a trembling upper lip" instead of "He was nervous").
- SUBTEXTUAL DIALOGUE: Characters must NEVER say exactly what they mean. Use subtext to create tension, mystery, and depth. Dialogue should be a chess match.
- CINEMATIC METAPHOR: Use environmental details (lighting, weather, specific props) to represent the internal state of the characters or the theme of the movie.
- RELENTLESS PACING: Each scene must start at the latest possible moment and end at the earliest possible moment. No filler. No wasted frames.
- CHARACTER VOICEPRINT: Ensure every character has a distinct linguistic DNA. One might use short, clipped sentences; another might be flowery and evasive.
- MUSIC AND SONGS: When appropriate, indicate music needs using cues like [MUSIC: style, duration] for instrumental segments, [SONG: lyrics] for musical numbers, [MUSICAL NUMBER] for full performances, or [MONTAGE] for montage sequences. Include lyrics when characters sing. Be creative - musical moments can enhance emotional impact, transitions, or character development.
- SCORE GOAL: Aim for a script that feels like an instant classic.
"""

system_prompt_template_write_script_based_on_story_shorts = \
"""
[Role]
You are a professional short-form script writer specializing in viral YouTube Shorts.

[Task]
Adapt the story into a single-scene script optimized for 15-35 seconds. The output must be a list containing exactly ONE scene.

[Input]
You will receive a story within <STORY> and </STORY> tags and a user requirement within <USER_REQUIREMENT> and </USER_REQUIREMENT> tags.
- The user requirement may include <CHARACTER_PROFILES> with personality, voice, role, and traits.

[Output]
{format_instructions}

[Guidelines]
- Output a single scene only (one location, continuous time).
- Keep dialogue extremely concise; favor action lines.
- Start with a hook line or action.
- Make every line visually filmable and fast-paced.
- Avoid camera jargon, voiceover format, or slow exposition.
- The language of output in values should match the input story.
- Character Voice: If <CHARACTER_PROFILES> are provided:
    - Match dialogue to each character's voice (curious vs sarcastic vs wise).
    - Keep characters in their roles (main_host leads, co_host reacts).
    - Use personality traits to inform quick reactions and one-liners.
"""


human_prompt_template_write_script_based_on_story = \
"""
<STORY>
{story}
</STORY>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>
"""

SCREENWRITER_PROFILES = {
    "feature_film": system_prompt_template_develop_story,
    "short_film": system_prompt_template_develop_story,
    "tv_series": """
[Role]
You are a legendary, Emmy-winning TV showrunner and elite screenwriter. You are the architect of "Peak TV," known for creating complex serial narratives and unforgettable character arcs.

[Task]
Generate a complete, engaging story for a TV series episode. Your goal is to achieve a 10/10 score by designing for relentless episodic hooks and profound character depth.

[Guidelines]
- ARCHITECTURAL PACING: Masterfully structure the episode. Use "Cold Opens" that shock and "Cliffhangers" that haunt.
- SEASONAL ARC: Ensure the story advances the "Grand Narrative" while delivering a satisfying standalone experience.
- CHARACTER DNA: Characters must have conflicting internal and external lives.
- SUBTEXT: Characters must NEVER say exactly what they feel.
""",
    "documentary": """
[Role]
You are a world-class documentary screenwriter and investigative journalist. You are known for your ability to find the profound "Human Story" within factual data and historical events.

[Task]
Generate a compelling documentary narrative. Your goal is to achieve a 10/10 score by delivering emotional truth, visceral evidence, and a powerful investigative arc.

[Guidelines]
- NARRATIVE TRUTH: Focus on real human stakes. Use interviews and evidence as dramatic beats.
- VISUAL EVIDENCE: Describe scenes that prove your narrative claims through cinematic verite.
- THEMATIC DEPTH: Explore the "Why" behind the facts.
- PACING: Use a mix of reflective quiet moments and high-intensity revelations.
""",
    "learning_series": """
[Role]
You are a legendary instructional designer and educational architect. You don't just teach; you architect intellectual breakthroughs through "Layered Learning."

[Task]
Generate a structured educational story/script. Your goal is to achieve a 10/10 score for learning retention and engagement.

[Guidelines]
- PEDAGOGICAL MASTERY: Every beat must have a learning purpose. 
- THE HOOK: Why does the learner's future depend on mastering this specific lesson?
- RELENTLESS APPLICATION: Integrate practical "Aha!" moments into the narrative.
- CLARITY: Use precise, evocative language to simplify complex systems.
""",
    "podcast": """
[Role]
You are a legendary, award-winning podcast showrunner. You don't just record conversations; you architect intellectual and emotional experiences that listeners obsess over.

[Task]
Generate a structured podcast narrative/script. Your goal is absolute listener retention and "Obsession-Worthiness."

[Guidelines]
- THE OBSESSION HOOK: The first 30 seconds must be so compelling that turning it off feels like a mistake.
- VOICEPRINT: Design hosts and guests with distinct, conflicting, and fascinating personalities.
- MIC-DROP IMPACT: Every insight must be delivered with maximum impact.
- PATTERN INTERRUPTS: Keep the energy relentless with dynamic segment shifts.
""",
    "ad": """
[Role]
You are an elite commercial creative director and copywriter. You are a master of "The 3-Second Hook" and "Visual Desire."

[Task]
Generate a high-conversion advertisement story. Your goal is 10/10 viral potential and immediate brand action.

[Guidelines]
- STOP THE SCROLL: The first frame must be a visual shock or a breathtaking "Hero" shot.
- BRAND AS STAR: The product/service must be the protagonist of the narrative.
- EMOTIONAL VELOCITY: Move the audience from "Curiosity" to "Desire" in seconds.
- CALL TO ACTION: The narrative must build relentless momentum towards the click.
""",
    "music_video": """
[Role]
You are a visionary music video director and storyteller. You are known for your "Visual Poetry" and "Rhythmic Narratives."

[Task]
Generate a story perfectly synced to musical rhythm. It must be iconic, experimental, and visually unforgettable.

[Guidelines]
- VISUAL POETRY: Use abstract metaphors to represent lyrics and mood.
- RHYTHMIC PACING: The story beats must align with the song's energy shifts.
- EXPERIMENTALISM: Defy narrative logic in favor of emotional and visual impact.
- ICONIC IMAGERY: Every scene must feel like a frame from a masterpiece.
"""
}


class Screenwriter(BaseAgent):
    def __init__(
        self,
        chat_model: str,
        shorts_mode: Optional[Dict] = None,
        pipeline_kind: str = "feature_film"
    ):
        super().__init__(chat_model)
        self.shorts_mode = shorts_mode or {}
        self.pipeline_kind = pipeline_kind if pipeline_kind in SCREENWRITER_PROFILES else "feature_film"

    async def develop_story(
        self,
        idea: str,
        user_requirement: Optional[str] = None,
    ) -> str:
        system_prompt = SCREENWRITER_PROFILES.get(self.pipeline_kind, system_prompt_template_develop_story)
        # Only use shorts prompt for actual short-form video content (TikTok/YouTube Shorts)
        # NOT for short films or feature films
        if self.shorts_mode.get("enabled") and self.shorts_mode.get("format") in ("shorts", "short_video", "tiktok", "youtube_shorts"):
            system_prompt = system_prompt_template_develop_story_shorts
        messages = [
            ("system", system_prompt),
            ("human", human_prompt_template_develop_story.format(idea=idea, user_requirement=user_requirement)),
        ]
        response = await self.chat_model.ainvoke(messages)
        story = response.content
        return story

    async def develop_movie_outline(
        self,
        story: str,
        target_runtime_minutes: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        Break a long story into chapters/segments (e.g., 10-minute blocks).
        Essential for scaling to 200-minute movies.
        """
        num_chapters = max(1, target_runtime_minutes // 10)
        
        class MovieChapter(BaseModel):
            chapter_number: int
            title: str
            summary: str
            target_minutes: int

        class MovieOutline(BaseModel):
            chapters: List[MovieChapter]

        parser = PydanticOutputParser(pydantic_object=MovieOutline)
        format_instructions = parser.get_format_instructions()

        system_prompt = f"""You are a professional film producer and script supervisor. 
Divide this story into {num_chapters} chapters/segments for a {target_runtime_minutes}-minute feature film.
Each chapter should represent approximately 10 minutes of screen time.
Ensure the three-act structure is maintained across these chapters.

{format_instructions}"""

        messages = [
            ("system", system_prompt),
            ("human", f"<STORY>\n{story}\n</STORY>"),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        try:
            parsed = parser.parse(response.content)
            return [c.model_dump() for c in parsed.chapters]
        except Exception as e:
            logging.error(f"Failed to parse movie outline: {e}. Falling back to single chapter.")
            return [{
                "chapter_number": 1,
                "title": "Full Story",
                "summary": story,
                "target_minutes": target_runtime_minutes
            }]

    async def write_script_for_chapter(
        self,
        story_context: str,
        chapter_info: Dict[str, Any],
        user_requirement: Optional[str] = None,
    ) -> List[str]:
        """Write detailed scenes for a specific chapter of a long movie."""
        chapter_title = chapter_info.get("title", "")
        chapter_summary = chapter_info.get("summary", "")
        chapter_num = chapter_info.get("chapter_number", 1)
        target_mins = chapter_info.get("target_minutes", 10)
        
        # Estimate 1-1.5 scenes per minute
        target_scenes = max(5, int(target_mins * 1.2))

        chapter_requirement = f"""
Write script for CHAPTER {chapter_num}: {chapter_title}.
Target Duration: {target_mins} minutes.
Number of Scenes to write: Approximately {target_scenes} scenes.
Context: {chapter_summary}

{user_requirement or ""}
"""
        return await self.write_script_based_on_story(
            story=story_context,
            user_requirement=chapter_requirement,
        )

    async def write_script_based_on_story(
        self,
        story: str,
        user_requirement: Optional[str] = None,
    ) -> List[str]:


        class WriteScriptBasedOnStoryResponse(BaseModel):
            script: List[str] = Field(
                ...,
                description="The script based on the story. Each element is a scene "
            )

        parser = PydanticOutputParser(pydantic_object=WriteScriptBasedOnStoryResponse)
        format_instructions = parser.get_format_instructions()

        base_script_prompt = system_prompt_template_write_script_based_on_story
        
        # Add profile-specific nuances to scriptwriting if needed
        profile_nuance = ""
        if self.pipeline_kind == "tv_series":
            profile_nuance = "\n- Focus on episodic cliffhangers and B-story integration."
        elif self.pipeline_kind == "learning_series":
            profile_nuance = "\n- Prioritize clear visual demonstration over dramatic dialogue."
        elif self.pipeline_kind == "podcast":
            profile_nuance = "\n- Focus on natural, conversational overlap and audio cues."
        elif self.pipeline_kind == "ad":
            profile_nuance = "\n- Focus on product placement and high-speed editing cues."
            
        system_prompt = base_script_prompt + profile_nuance
        
        # Only use shorts prompt for actual short-form video content (TikTok/YouTube Shorts)
        # NOT for short films or feature films
        if self.shorts_mode.get("enabled") and self.shorts_mode.get("format") in ("shorts", "short_video", "tiktok", "youtube_shorts"):
            system_prompt = system_prompt_template_write_script_based_on_story_shorts
        messages = [
            ("system", system_prompt.format(format_instructions=format_instructions)),
            ("human", human_prompt_template_write_script_based_on_story.format(story=story, user_requirement=user_requirement)),
        ]
        response = await self.chat_model.ainvoke(messages)
        
        import logging
        import re
        logger = logging.getLogger(__name__)
        
        # Try to parse the response
        try:
            # Handle empty/null response
            if not response.content or response.content.strip() in ("", "null", "None"):
                raise ValueError("LLM returned empty/null response")
            parsed = parser.parse(response.content)
            return parsed.script
        except Exception as e:
            logger.warning(f"Script parsing failed: {e}. Response was: {response.content[:500] if response.content else 'None'}...")
            logger.warning("Attempting retry with simplified prompt...")
            
            # Retry with a simpler prompt
            simple_messages = [
                ("system", "You are a professional screenwriter. Convert the story into a screenplay with scene-by-scene scripts. Output valid JSON: {\"script\": [\"SCENE 1: ...\", \"SCENE 2: ...\", ...]}"),
                ("human", f"Convert this story into screenplay scenes:\n\n{story[:8000]}"),
            ]
            try:
                response = await self.chat_model.ainvoke(simple_messages)
                if response.content and response.content.strip() not in ("", "null", "None"):
                    parsed = parser.parse(response.content)
                    return parsed.script
            except Exception as e2:
                logger.warning(f"Retry also failed: {e2}")
            
            # Last resort: return story split into scenes
            logger.warning("Falling back to splitting story into basic scenes.")
            scenes = re.split(r'\n(?=Scene\s+\w+:|ACT\s+\d|INT\.|EXT\.)', story)
            return [s.strip() for s in scenes if s.strip()]
