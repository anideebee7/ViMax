"""
Pipeline-specific agent profiles and visual direction configurations.

Each pipeline type has optimized settings for:
- Visual direction and cinematography
- Content goals (engagement, conversions, education)
- Pacing and duration guidelines
- Platform-specific optimizations
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class VisualProfile:
    """Visual direction profile for a content type."""
    
    # Camera and composition
    camera_style: str = ""
    framing_guidelines: List[str] = field(default_factory=list)
    movement_style: str = ""
    
    # Lighting and atmosphere
    lighting_style: str = ""
    color_palette: str = ""
    atmosphere: str = ""
    
    # Pacing
    cut_rhythm: str = ""
    avg_shot_duration_seconds: float = 3.0
    transition_style: str = ""
    
    # Environment
    environment_type: str = ""
    background_style: str = ""
    
    def to_prompt(self) -> str:
        """Convert to prompt string for agents."""
        lines = []
        if self.camera_style:
            lines.append(f"Camera Style: {self.camera_style}")
        if self.framing_guidelines:
            lines.append(f"Framing: {', '.join(self.framing_guidelines)}")
        if self.movement_style:
            lines.append(f"Movement: {self.movement_style}")
        if self.lighting_style:
            lines.append(f"Lighting: {self.lighting_style}")
        if self.color_palette:
            lines.append(f"Colors: {self.color_palette}")
        if self.atmosphere:
            lines.append(f"Atmosphere: {self.atmosphere}")
        if self.cut_rhythm:
            lines.append(f"Pacing: {self.cut_rhythm}")
        if self.environment_type:
            lines.append(f"Environment: {self.environment_type}")
        return "\n".join(lines)


@dataclass
class ContentGoals:
    """Content-specific goals for optimization."""
    
    primary_goal: str = ""  # engagement, conversion, education, entertainment
    success_metrics: List[str] = field(default_factory=list)
    call_to_action_style: str = ""
    hook_duration_seconds: float = 3.0
    retention_strategy: str = ""
    
    def to_prompt(self) -> str:
        """Convert to prompt string."""
        lines = [f"Primary Goal: {self.primary_goal}"]
        if self.success_metrics:
            lines.append(f"Optimize for: {', '.join(self.success_metrics)}")
        if self.call_to_action_style:
            lines.append(f"CTA Style: {self.call_to_action_style}")
        if self.retention_strategy:
            lines.append(f"Retention: {self.retention_strategy}")
        return "\n".join(lines)


@dataclass
class PipelineProfile:
    """Complete profile for a pipeline type."""
    
    name: str
    description: str
    visual_profile: VisualProfile
    content_goals: ContentGoals
    
    # Agent-specific instructions
    screenwriter_instructions: str = ""
    storyboard_instructions: str = ""
    director_instructions: str = ""
    
    # Platform optimization
    target_platforms: List[str] = field(default_factory=list)
    platform_optimizations: Dict[str, str] = field(default_factory=dict)
    
    # Duration settings
    min_duration_seconds: int = 30
    max_duration_seconds: int = 300
    optimal_duration_seconds: int = 60
    
    # Special features
    special_features: List[str] = field(default_factory=list)
    
    def get_full_context(self) -> str:
        """Get complete context block for agents."""
        sections = [
            f"<PIPELINE_PROFILE type='{self.name}'>",
            f"Description: {self.description}",
            "",
            "<VISUAL_DIRECTION>",
            self.visual_profile.to_prompt(),
            "</VISUAL_DIRECTION>",
            "",
            "<CONTENT_GOALS>",
            self.content_goals.to_prompt(),
            "</CONTENT_GOALS>",
        ]
        
        if self.screenwriter_instructions:
            sections.extend([
                "",
                "<SCREENWRITER_GUIDELINES>",
                self.screenwriter_instructions,
                "</SCREENWRITER_GUIDELINES>",
            ])
        
        if self.storyboard_instructions:
            sections.extend([
                "",
                "<STORYBOARD_GUIDELINES>",
                self.storyboard_instructions,
                "</STORYBOARD_GUIDELINES>",
            ])
        
        if self.director_instructions:
            sections.extend([
                "",
                "<DIRECTOR_GUIDELINES>",
                self.director_instructions,
                "</DIRECTOR_GUIDELINES>",
            ])
        
        if self.target_platforms:
            sections.extend([
                "",
                f"Target Platforms: {', '.join(self.target_platforms)}",
            ])
            for platform, opt in self.platform_optimizations.items():
                sections.append(f"  {platform}: {opt}")
        
        sections.append("</PIPELINE_PROFILE>")
        return "\n".join(sections)


# =============================================================================
# PIPELINE PROFILES - Ultra-customized for each content type
# =============================================================================

PODCAST_PROFILE = PipelineProfile(
    name="podcast2video",
    description="Podcast episodes with talking characters in consistent studio setting",
    visual_profile=VisualProfile(
        camera_style="Studio multi-cam setup with 3 fixed positions",
        framing_guidelines=[
            "Master shot: Wide view of all characters in studio",
            "Single shots: Medium close-up for speaking character",
            "Two-shots: Characters engaging in conversation",
            "Cutaways: Visual aids, graphics, or reaction shots",
        ],
        movement_style="Minimal camera movement - smooth slow pans/zooms only",
        lighting_style="Warm studio lighting with soft key lights, colorful accents",
        color_palette="Vibrant but consistent studio colors, character-matched backgrounds",
        atmosphere="Warm, inviting, conversational energy",
        cut_rhythm="Conversation-driven cuts, 3-5 seconds per shot, cut on speaker changes",
        avg_shot_duration_seconds=4.0,
        transition_style="Simple cuts, occasional soft dissolves for topic transitions",
        environment_type="Consistent podcast studio set - same background throughout",
        background_style="Studio backdrop with subtle animations, character-themed decorations",
    ),
    content_goals=ContentGoals(
        primary_goal="engagement",
        success_metrics=["watch time", "subscriber conversion", "comment engagement"],
        call_to_action_style="Warm reminder to subscribe, gentle and friendly",
        hook_duration_seconds=5.0,
        retention_strategy="Topic previews, chapter markers, personality-driven content",
    ),
    screenwriter_instructions="""
- Characters should stay in-studio throughout (no location changes)
- Dialogue-heavy with natural conversation flow
- Include reaction shots and character interactions
- Build rapport between characters
- Use visual aids/graphics for complex topics
- Maintain consistent character positions (host center, guests sides)
- Include natural pauses and thinking moments
""",
    storyboard_instructions="""
- Studio background must remain CONSISTENT across all shots
- Characters only move within their designated areas (sitting/standing positions)
- Focus on facial expressions and gestures for engagement
- Use split-screen for multiple speakers occasionally
- Include lower-thirds for speaker identification
- Visual aids appear on-screen, not requiring character movement
""",
    director_instructions="""
- CRITICAL: Background never changes - same studio throughout
- Characters may gesture, lean, turn, but don't walk around
- Emphasize personality through expression, not movement
- Cut rhythm follows conversation flow
- B-roll should be overlays, not location changes
""",
    target_platforms=["YouTube", "Spotify Video", "Apple Podcasts"],
    platform_optimizations={
        "YouTube": "Longer episodes (15-45 min), chapters, end screens",
        "Spotify": "Audio-first design, visual companion",
        "Shorts": "Clip best moments for 30-60 second highlights",
    },
    min_duration_seconds=300,
    max_duration_seconds=3600,
    optimal_duration_seconds=1200,
    special_features=["consistent_background", "character_positions_fixed", "dialogue_focused"],
)

DOCUMENTARY_PROFILE = PipelineProfile(
    name="documentary",
    description="Documentary content - can be animated, real-world, historical, or sci-fi",
    visual_profile=VisualProfile(
        camera_style="Cinematic documentary style - varied based on subject matter",
        framing_guidelines=[
            "Establishing shots: Wide scenic/contextual views",
            "Interview frames: Rule-of-thirds, medium shots",
            "B-roll: Dynamic shots showing subject matter",
            "Archive footage style: Period-appropriate look",
            "Animated sequences: Illustrative and explanatory",
        ],
        movement_style="Purposeful movements - Ken Burns effect on stills, smooth tracking for motion",
        lighting_style="Natural/available light feel, dramatic when needed for tone",
        color_palette="Subject-appropriate: desaturated for historical, vibrant for nature, cool for sci-fi",
        atmosphere="Authoritative yet engaging, educational but emotional",
        cut_rhythm="Information-paced, longer shots for contemplation, quick cuts for energy",
        avg_shot_duration_seconds=5.0,
        transition_style="Purposeful transitions - dissolves for time, cuts for energy, wipes for location",
        environment_type="Varies by subject: real locations, animated worlds, archival settings, sci-fi environments",
        background_style="Authentic to subject matter - researched and period-accurate or imaginatively created",
    ),
    content_goals=ContentGoals(
        primary_goal="education",
        success_metrics=["completion rate", "shares", "educational value", "authority building"],
        call_to_action_style="Thought-provoking conclusion, invitation to learn more",
        hook_duration_seconds=8.0,
        retention_strategy="Story arc, revelations, expert insights, emotional moments",
    ),
    screenwriter_instructions="""
- Structure with clear narrative arc (setup, conflict/exploration, resolution/insight)
- Balance facts with storytelling
- Include expert perspectives or character insights
- Use chapter/segment structure for longer content
- Build emotional connection to subject matter
- End with meaningful conclusion or call to reflection
- Can be told through:
  * Animated characters explaining concepts
  * Real-world footage and interviews
  * Historical recreations
  * Sci-fi/speculative scenarios
  * Nature/wildlife storytelling
""",
    storyboard_instructions="""
- Establish visual world clearly in opening
- Vary visual approach based on content type:
  * Animated: Expressive characters, clear visual metaphors
  * Real-world: Authentic locations, interview setups
  * Historical: Period-accurate aesthetics, archival integration
  * Sci-fi: Imaginative world-building, futuristic elements
- Use graphics and animations for data visualization
- Include breathing room for emotional moments
""",
    director_instructions="""
- Visual style should match subject gravity
- Pace reveals and information for maximum impact
- Use music strategically for emotional beats
- Balance talking heads with dynamic visuals
- Create visual variety while maintaining coherent style
""",
    target_platforms=["YouTube", "Netflix/Streaming", "Educational Platforms"],
    platform_optimizations={
        "YouTube": "Chapters, SEO-optimized titles, community engagement",
        "Streaming": "Higher production value, binge-worthy structure",
        "Educational": "Learning objectives, assessments, supplementary materials",
    },
    min_duration_seconds=600,
    max_duration_seconds=7200,
    optimal_duration_seconds=1800,
    special_features=["multi_visual_style", "narrative_arc", "expert_integration"],
)

KIDS_MOVIE_PROFILE = PipelineProfile(
    name="kids_movie",
    description="Animated kids content - colorful, engaging, age-appropriate with moral lessons",
    visual_profile=VisualProfile(
        camera_style="Dynamic animated camera - expressive, playful movements",
        framing_guidelines=[
            "Wide shots: Establish magical/fun environments",
            "Character shots: Big expressions, clear emotions",
            "Action shots: Dynamic angles for excitement",
            "Reaction shots: Exaggerated for comedy/emotion",
        ],
        movement_style="Bouncy, energetic camera movements that match character energy",
        lighting_style="Bright, cheerful lighting with magical glows and sparkles",
        color_palette="Vibrant, saturated colors - each character has distinct palette",
        atmosphere="Magical, fun, safe, and wonder-filled",
        cut_rhythm="Energetic but not overwhelming, matches music and action",
        avg_shot_duration_seconds=2.5,
        transition_style="Fun wipes, magical transitions, character-driven scene changes",
        environment_type="Colorful animated worlds - forests, castles, space, underwater, cities",
        background_style="Detailed but not distracting, supports character focus",
    ),
    content_goals=ContentGoals(
        primary_goal="entertainment",
        success_metrics=["rewatch rate", "merchandise potential", "parent approval", "sing-along moments"],
        call_to_action_style="Gentle lesson reinforcement, invitation to imagine",
        hook_duration_seconds=3.0,
        retention_strategy="Songs, lovable characters, humor, relatable situations",
    ),
    screenwriter_instructions="""
- Age-appropriate language and themes
- Clear moral/lesson woven into story (not preachy)
- Lovable, distinct characters with clear personalities
- Include moments of:
  * Humor (visual and verbal)
  * Heart (emotional connection)
  * Adventure (exciting sequences)
  * Music (if applicable)
- Villain/conflict should be scary but not traumatizing
- Resolution should be satisfying and positive
- Characters should model good behavior naturally
""",
    storyboard_instructions="""
- Characters must be expressive and readable from any angle
- Backgrounds should be colorful but not overwhelm characters
- Action should be clear and easy to follow
- Include quieter moments between high-energy sequences
- Visual humor through character animation
- Safe and appropriate imagery at all times
""",
    director_instructions="""
- Pacing must match child attention spans
- Emotional beats should be clear and not subtle
- Songs/musical moments get special visual treatment
- Keep scary moments brief and resolved quickly
- Celebrate character victories enthusiastically
- End on positive, uplifting note
""",
    target_platforms=["YouTube Kids", "Netflix Kids", "Disney+", "Educational TV"],
    platform_optimizations={
        "YouTube Kids": "Bright thumbnails, clear titles, no scary content",
        "Streaming": "Series potential, character merchandise tie-ins",
        "Educational": "Learning objectives subtly integrated",
    },
    min_duration_seconds=300,
    max_duration_seconds=5400,
    optimal_duration_seconds=1200,
    special_features=["age_appropriate", "moral_lesson", "character_merchandise", "musical_potential"],
)

AD_PROFILE = PipelineProfile(
    name="ad",
    description="Advertisement videos optimized for app downloads, product sales, and conversions",
    visual_profile=VisualProfile(
        camera_style="High-impact commercial cinematography - polished and professional",
        framing_guidelines=[
            "Product hero shots: Clean, well-lit, aspirational",
            "User/lifestyle shots: Relatable, authentic feeling",
            "App UI shots: Clear, smooth, device-framed",
            "Before/after: Clear transformation visuals",
        ],
        movement_style="Dynamic but controlled - smooth tracks, punchy zooms",
        lighting_style="Premium commercial lighting - clean, bright, professional",
        color_palette="Brand-aligned colors, high contrast for impact",
        atmosphere="Aspirational, energetic, trustworthy",
        cut_rhythm="FAST - 1-2 seconds per cut, build to CTA",
        avg_shot_duration_seconds=1.5,
        transition_style="Punchy cuts, motion graphics transitions, kinetic typography",
        environment_type="Lifestyle contexts where product shines",
        background_style="Clean, uncluttered, product-focused",
    ),
    content_goals=ContentGoals(
        primary_goal="conversion",
        success_metrics=["click-through rate", "app downloads", "purchases", "ROAS"],
        call_to_action_style="CLEAR and URGENT - Download now, Shop now, Limited time",
        hook_duration_seconds=1.5,
        retention_strategy="Problem-solution narrative, social proof, urgency",
    ),
    screenwriter_instructions="""
- Hook in FIRST 1.5 SECONDS - stop the scroll
- Structure for conversions:
  1. Hook: Attention-grabbing opening (problem or aspiration)
  2. Problem: Relatable pain point (2-5 seconds)
  3. Solution: Product as hero (5-15 seconds)
  4. Proof: Social proof, reviews, results (5-10 seconds)
  5. CTA: Clear action with urgency (3-5 seconds)
- Include:
  * Specific benefits, not features
  * Numbers and statistics when available
  * User testimonials or social proof
  * Urgency elements (limited time, scarcity)
  * Clear value proposition
- Avoid: Vague claims, slow pacing, buried CTA
""",
    storyboard_instructions="""
- EVERY frame must serve conversion goal
- Product must be hero - large, clear, desirable
- For apps: Show actual UI, smooth interactions
- For products: Lifestyle context + product detail shots
- Text overlays: Large, readable, high contrast
- Include price/offer prominently
- End frame: Logo + CTA + download/buy info
""",
    director_instructions="""
- PACING IS EVERYTHING - no dead moments
- Every second must earn its place
- Music: Energetic, builds to CTA
- Sound design: Satisfying UI sounds, impact sounds
- A/B variants should test different:
  * Hooks (problem vs aspiration)
  * CTAs (urgency vs benefit)
  * Visuals (lifestyle vs product-focused)
- Track performance and iterate
""",
    target_platforms=["TikTok", "Instagram", "Facebook", "YouTube Ads", "Google Display"],
    platform_optimizations={
        "TikTok": "Native feel, trending sounds, UGC aesthetic",
        "Instagram": "Polished, aesthetic, aspirational",
        "Facebook": "Broader appeal, clear value prop, social proof",
        "YouTube Pre-roll": "Hook in 5 seconds, skippable-optimized",
        "Google Display": "Clear product, strong CTA, minimal text",
    },
    min_duration_seconds=6,
    max_duration_seconds=60,
    optimal_duration_seconds=15,
    special_features=["ab_testing", "conversion_tracking", "urgency_elements", "social_proof"],
)

SHORT_MOVIE_PROFILE = PipelineProfile(
    name="short_movie",
    description="Cinematic short films (5-20 min) - narrative storytelling with film quality",
    visual_profile=VisualProfile(
        camera_style="Cinematic film language - intentional, story-driven choices",
        framing_guidelines=[
            "Establishing: Set tone and location",
            "Character work: Intimate medium shots, meaningful close-ups",
            "Action: Dynamic angles, coverage for editing",
            "Emotional beats: Breathing room, lingering shots",
        ],
        movement_style="Motivated movement - dollies, steadicam, handheld when story demands",
        lighting_style="Cinematic lighting - motivated sources, mood-driven",
        color_palette="Film-graded look, consistent tone throughout",
        atmosphere="Immersive, emotionally engaging, film-quality",
        cut_rhythm="Story-driven editing - lingering when needed, rhythmic in action",
        avg_shot_duration_seconds=4.0,
        transition_style="Invisible cuts, motivated transitions, match cuts for art",
        environment_type="Locations that serve story - authentic or stylized",
        background_style="Production-designed, meaningful details",
    ),
    content_goals=ContentGoals(
        primary_goal="entertainment",
        success_metrics=["festival selection", "emotional impact", "artistic merit", "shareability"],
        call_to_action_style="None needed - let the film speak",
        hook_duration_seconds=10.0,
        retention_strategy="Character investment, rising tension, emotional payoff",
    ),
    screenwriter_instructions="""
- Three-act structure even in short form
- Character arc is essential - transformation
- Show don't tell - visual storytelling
- Subtext in dialogue
- Theme should resonate universally
- Ending should be earned and impactful
- Genre conventions can be used or subverted
- Budget-conscious writing (limited locations, small cast)
""",
    storyboard_instructions="""
- Every shot should be intentional
- Coverage for editing flexibility
- Establish visual motifs
- Plan for emotional beats
- Consider practical execution
- Visual symbolism and metaphor
""",
    director_instructions="""
- Performances are everything
- Pacing serves emotional journey
- Sound design is half the experience
- Music should enhance, not override
- Leave room for audience interpretation
- End strong - last image matters
""",
    target_platforms=["Film Festivals", "YouTube", "Vimeo", "Streaming Short Film Sections"],
    platform_optimizations={
        "Festivals": "Festival-ready format, no watermarks, proper credits",
        "YouTube": "Premiere strategy, community building",
        "Vimeo": "Quality player, filmmaker community",
    },
    min_duration_seconds=300,
    max_duration_seconds=1200,
    optimal_duration_seconds=720,
    special_features=["three_act_structure", "character_arc", "festival_ready"],
)

MUSIC_VIDEO_PROFILE = PipelineProfile(
    name="song2musicvideo",
    description="Music video production - visual interpretation of music",
    visual_profile=VisualProfile(
        camera_style="Genre-appropriate - performance shots, narrative, or abstract",
        framing_guidelines=[
            "Performance: Dynamic angles, artist as hero",
            "Narrative: Cinematic coverage for story",
            "Abstract: Artistic compositions, visual metaphors",
            "Cutaways: Symbolic imagery, detail shots",
        ],
        movement_style="Music-driven - beat-synced movements, energy matching",
        lighting_style="Stylized, dramatic, mood-creating - concert/music video look",
        color_palette="Bold, striking, music-genre appropriate",
        atmosphere="Immersive audiovisual experience",
        cut_rhythm="MUSIC-DRIVEN - cuts on beats, flow with song structure",
        avg_shot_duration_seconds=2.0,
        transition_style="Beat-matched cuts, creative transitions, visual effects",
        environment_type="Stylized sets, real locations, abstract spaces",
        background_style="Visually striking, supports music mood",
    ),
    content_goals=ContentGoals(
        primary_goal="engagement",
        success_metrics=["views", "shares", "playlist adds", "fan engagement"],
        call_to_action_style="Stream links, follow artist, concert info",
        hook_duration_seconds=3.0,
        retention_strategy="Visual interest throughout, narrative/performance peaks",
    ),
    screenwriter_instructions="""
- Lyrics should guide visual narrative
- Verse/chorus structure reflected in visuals
- Performance sections for artist connection
- Narrative/story if lyrics support it
- Visual metaphors for abstract lyrics
- Bridge = visual climax opportunity
- Song structure drives scene structure
""",
    storyboard_instructions="""
- Map shots to song timestamp
- Cut points aligned with beats/measures
- Chorus gets repeated visual treatment
- Build visual energy with song
- Artist/band always look good
- Plan for music sync in editing
""",
    director_instructions="""
- EVERYTHING syncs to music
- Energy ebbs and flows with song
- Performance must feel authentic
- Narrative complements, doesn't overshadow
- Visual spectacle for shareability
- End on memorable image
""",
    target_platforms=["YouTube Music", "Vevo", "TikTok", "Instagram Reels"],
    platform_optimizations={
        "YouTube": "Full video, premiere event, lyric overlays option",
        "TikTok": "15-30 second viral clips",
        "Instagram": "Reels clips, aesthetic moments",
    },
    min_duration_seconds=120,
    max_duration_seconds=420,
    optimal_duration_seconds=210,
    special_features=["music_sync", "performance_narrative_hybrid", "viral_clips"],
)

LEARNING_SERIES_PROFILE = PipelineProfile(
    name="learning_series",
    description="Educational video series - structured learning with engaging delivery",
    visual_profile=VisualProfile(
        camera_style="Educational broadcast style - clear, professional, approachable",
        framing_guidelines=[
            "Instructor shots: Medium shots, friendly eye contact",
            "Content visuals: Clear diagrams, animations, demonstrations",
            "Screen recordings: Clean UI, highlighted interactions",
            "Supporting visuals: Examples, case studies, real-world applications",
        ],
        movement_style="Steady, professional - subtle movements only",
        lighting_style="Bright, even, no harsh shadows - broadcast quality",
        color_palette="Professional, brand-consistent, easy on eyes",
        atmosphere="Welcoming, authoritative, encouraging",
        cut_rhythm="Information-paced, time for comprehension",
        avg_shot_duration_seconds=6.0,
        transition_style="Clean cuts, occasional wipes for topic shifts",
        environment_type="Studio, classroom, or relevant environment",
        background_style="Clean, branded, not distracting",
    ),
    content_goals=ContentGoals(
        primary_goal="education",
        success_metrics=["completion rate", "quiz scores", "skill application", "course completion"],
        call_to_action_style="Continue learning, practice exercises, next lesson",
        hook_duration_seconds=5.0,
        retention_strategy="Clear objectives, progress tracking, practical exercises",
    ),
    screenwriter_instructions="""
- Clear learning objectives stated upfront
- Structured progression:
  * Hook: Why this matters
  * Teach: Core concept explanation
  * Show: Examples and demonstrations
  * Practice: Exercises or applications
  * Recap: Key takeaways
- Chunk information appropriately
- Build on previous episodes
- Include knowledge checks
- End with clear next steps
""",
    storyboard_instructions="""
- Visual aids must clarify, not decorate
- Text on screen supports spoken content
- Diagrams progress step-by-step
- Screen recordings have clear focus
- Instructor presence builds connection
- Consistent visual language throughout series
""",
    director_instructions="""
- Pacing allows comprehension
- Energy maintains engagement without rushing
- Repeat key points visually and verbally
- Practical examples are essential
- Celebrate small wins and progress
- Series consistency in style and tone
""",
    target_platforms=["YouTube", "Udemy", "Skillshare", "Coursera", "Internal LMS"],
    platform_optimizations={
        "YouTube": "Playlist structure, timestamps, community engagement",
        "Course Platforms": "Quiz integration, certificates, assignments",
        "Corporate": "Measurable outcomes, compliance tracking",
    },
    min_duration_seconds=300,
    max_duration_seconds=1200,
    optimal_duration_seconds=600,
    special_features=["curriculum_structure", "progress_tracking", "assessments"],
)

SHORTS_PROFILE = PipelineProfile(
    name="video_shorts",
    description="Viral short-form video (15-60s) for TikTok, YouTube Shorts, Reels",
    visual_profile=VisualProfile(
        camera_style="Dynamic, attention-grabbing, pattern-interrupt",
        framing_guidelines=[
            "Vertical format (9:16) optimized",
            "Face/subject fills frame",
            "Text safe zones respected",
            "No wasted screen real estate",
        ],
        movement_style="Fast, energetic, constant motion",
        lighting_style="Bright, punchy, high contrast",
        color_palette="Vibrant, saturated, scroll-stopping",
        atmosphere="High energy, dopamine-inducing",
        cut_rhythm="RAPID - 0.5-2 seconds per cut maximum",
        avg_shot_duration_seconds=1.0,
        transition_style="Jump cuts, zoom transitions, matched action",
        environment_type="Varied, visually interesting, simple backgrounds",
        background_style="Clean but interesting, not distracting from content",
    ),
    content_goals=ContentGoals(
        primary_goal="engagement",
        success_metrics=["watch time", "shares", "follows", "saves", "algorithm favor"],
        call_to_action_style="Soft CTA - follow for more, link in bio",
        hook_duration_seconds=1.0,
        retention_strategy="Pattern interrupts, loops, curiosity gaps",
    ),
    screenwriter_instructions="""
- HOOK IN FIRST 0.5-1 SECOND - stop the scroll
- Structure for retention:
  * Hook: Unexpected opening
  * Promise: What viewer will get
  * Deliver: Fast-paced value
  * Loop: End connects to beginning for rewatches
- Speak directly to viewer
- Create curiosity gaps
- Use trending formats/sounds when relevant
- Every second must earn its place
- End with rewatch potential (loop, cliffhanger, satisfying conclusion)
""",
    storyboard_instructions="""
- Vertical composition (9:16)
- Face/subject prominent
- Text overlays in safe zones
- Visual interest in every frame
- Quick cuts planned
- Thumbnail-worthy frames
""",
    director_instructions="""
- NO SLOW MOMENTS
- First frame is everything
- Sound design is critical (trending sounds)
- Captions always on
- Pattern interrupts every 3-5 seconds
- End frame encourages rewatch or share
""",
    target_platforms=["TikTok", "YouTube Shorts", "Instagram Reels"],
    platform_optimizations={
        "TikTok": "Trending sounds, duet-able, native feel",
        "YouTube Shorts": "Clear value, subscribe prompt",
        "Instagram Reels": "Aesthetic, shareable to Stories",
    },
    min_duration_seconds=15,
    max_duration_seconds=60,
    optimal_duration_seconds=30,
    special_features=["vertical_format", "loop_friendly", "trending_sound_ready"],
)


# =============================================================================
# PROFILE REGISTRY - Easy access to all profiles
# =============================================================================

PIPELINE_PROFILES: Dict[str, PipelineProfile] = {
    "podcast2video": PODCAST_PROFILE,
    "documentary": DOCUMENTARY_PROFILE,
    "kids_movie": KIDS_MOVIE_PROFILE,
    "ad": AD_PROFILE,
    "short_movie": SHORT_MOVIE_PROFILE,
    "song2musicvideo": MUSIC_VIDEO_PROFILE,
    "learning_series": LEARNING_SERIES_PROFILE,
    "video_shorts": SHORTS_PROFILE,
    "video": PipelineProfile(
        name="video",
        description="General video content - flexible for various purposes",
        visual_profile=VisualProfile(
            camera_style="Versatile - matches content needs",
            lighting_style="Appropriate for subject",
            atmosphere="Content-appropriate",
        ),
        content_goals=ContentGoals(
            primary_goal="engagement",
            success_metrics=["views", "engagement", "shares"],
        ),
    ),
}


def get_pipeline_profile(pipeline_name: str) -> Optional[PipelineProfile]:
    """Get profile for a specific pipeline."""
    return PIPELINE_PROFILES.get(pipeline_name)


def get_profile_context(pipeline_name: str) -> str:
    """Get the full context string for a pipeline."""
    profile = get_pipeline_profile(pipeline_name)
    if profile:
        return profile.get_full_context()
    return ""
