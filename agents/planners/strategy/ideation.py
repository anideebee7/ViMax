"""IdeationEngine - Auto-generates content ideas based on various modes."""

import logging
import random
from typing import List, Optional, Literal
from langchain.chat_models.base import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from interfaces.entities.ideation import IdeationResult, PodcastEpisodeIdea, SeriesIdeation
from interfaces.output.monetization import TrendContext
from interfaces.entities.brand_context import BrandContext, GameContext

logger = logging.getLogger(__name__)


# Creativity prompts for different content types
CREATIVITY_SEEDS = {
    "video": [
        "An unexpected perspective on everyday objects",
        "A day in the life of an unusual profession",
        "What if technology could read emotions?",
        "The secret world that exists when no one is watching",
        "A journey through time in just 60 seconds",
        "The most satisfying process you've never seen",
        "What your pets really think about you",
        "The hidden mathematics in nature",
        "Strangest cultural traditions around the world",
        "What happens when AI dreams?",
    ],
    "shorts": [
        "One simple trick that changes everything",
        "The moment you realize...",
        "POV: You discover something unexpected",
        "Things that just hit different",
        "Wait for it...",
        "Nobody talks about this",
        "The truth about...",
        "Why does this work so well?",
        "This shouldn't be possible but...",
        "The most underrated...",
    ],
    "song": [
        "A love letter to the city at 3am",
        "The feeling of coming home after years away",
        "Dancing alone in your room when no one's watching",
        "The conversation you wish you had",
        "Chasing dreams that keep running away",
        "The last summer before everything changed",
        "Finding beauty in the ordinary chaos",
        "A anthem for the quietly ambitious",
        "The soundtrack to a road trip with strangers",
        "What your heart sounds like when it's healing",
    ],
    "documentary": [
        "The untold story behind a famous invention",
        "A community that lives completely off-grid",
        "The psychology of viral phenomena",
        "How one small decision changed history",
        "The last practitioner of a dying art",
        "The hidden economy you interact with daily",
        "What we can learn from failed experiments",
        "The science of what makes us happy",
        "Unsung heroes who changed your daily life",
        "The future that was promised vs reality",
    ],
    "ad": [
        "Show the transformation, not just the product",
        "Feature real customer stories with raw emotion",
        "Demonstrate unexpected uses of the product",
        "Create a mini-story with the product as hero",
        "Use humor to address common pain points",
        "Show the before/after in real-time",
        "Feature the product in an unusual setting",
        "Create ASMR-style product showcase",
        "Tell the origin story of the brand",
        "Show how the product connects people",
    ],
    "podcast": [
        "Interview someone who changed careers dramatically",
        "Deep dive into a topic everyone thinks they understand",
        "Debate format on a controversial opinion",
        "Behind the scenes of an interesting industry",
        "Life lessons from unexpected sources",
        "The science behind common myths",
        "Conversations with people who failed forward",
        "Exploring niche hobbies that have huge communities",
        "What experts wish the public understood",
        "Stories of serendipity that changed lives",
    ],
    "kids": [
        "A robot learning about human emotions",
        "Animals teaching valuable life lessons",
        "A magical world inside everyday objects",
        "Friends solving problems together",
        "Learning about different cultures through adventure",
        "Science experiments with surprising results",
        "The importance of kindness and sharing",
        "Overcoming fears with courage and friendship",
        "Environmental heroes saving the planet",
        "The power of imagination and creativity",
    ],
}

VIRALITY_FACTORS = [
    "Emotional surprise or twist",
    "Relatable 'that's so me' moment",
    "Satisfying visual or audio",
    "Controversy or hot take",
    "Educational 'I never knew' revelation",
    "Nostalgia trigger",
    "Fear of missing out (FOMO)",
    "Inspirational transformation",
    "Humor that catches off guard",
    "Social validation opportunity",
    "Challenge or trend participation",
    "Behind-the-scenes exclusive",
]


system_prompt_ideation = """
[Role]
You are a creative content ideation expert with deep understanding of viral content, audience psychology, and trending topics. You excel at generating fresh, engaging content ideas that resonate with specific audiences.

[Task]
Generate a compelling content idea based on the provided mode and context. Your idea should be:
- Original and attention-grabbing
- Tailored to the specified content type and audience
- Optimized for the target platform
- Aligned with current trends when applicable

[Ideation Modes]
- creativity: Pure creative generation, focus on originality and surprise
- trends: Based on current trending topics and hashtags
- viral: Optimized for shareability and engagement
- brand: Aligned with brand identity and values
- podcast: Suitable for audio/visual podcast format

[Input]
You will receive:
- Ideation mode within <MODE> tags
- Content type within <CONTENT_TYPE> tags
- Optional trend context within <TRENDS> tags
- Optional brand context within <BRAND_CONTEXT> tags
- Optional creative seed within <SEED> tags
- Target audience within <AUDIENCE> tags (if specified)

[Output]
{format_instructions}

[Guidelines]
- Make ideas specific and actionable, not vague
- Include hooks that grab attention in first 3 seconds
- Consider platform-specific best practices
- Think about shareability and comment-worthy moments
- For viral mode, include elements that encourage engagement
- For trends mode, naturally incorporate trending topics
- For brand mode, stay true to brand voice and values
"""

human_prompt_ideation = """
<MODE>
{mode}
</MODE>

<CONTENT_TYPE>
{content_type}
</CONTENT_TYPE>

<AUDIENCE>
{audience}
</AUDIENCE>

{trend_context}

{brand_context}

{seed_context}

Generate a compelling {content_type} idea optimized for {mode} mode.
"""


class IdeationEngine:
    """Engine for auto-generating content ideas."""
    
    def __init__(self, chat_model: BaseChatModel):
        self.chat_model = chat_model
    
    async def ideate(
        self,
        content_type: Literal["video", "shorts", "song", "documentary", "ad", "podcast", "kids", "learning", "movie", "short_movie", "music_video", "lyrics"],
        mode: Literal["creativity", "trends", "viral", "brand", "podcast"] = "creativity",
        audience: Optional[str] = None,
        trend_context: Optional[TrendContext] = None,
        brand_context: Optional[BrandContext] = None,
        game_context: Optional[GameContext] = None,
        creative_seed: Optional[str] = None,
    ) -> IdeationResult:
        """
        Generate a content idea based on the specified mode.
        
        Args:
            content_type: Type of content to ideate for
            mode: Ideation mode (creativity, trends, viral, brand, podcast)
            audience: Target audience description
            trend_context: Current trend data if available
            brand_context: Brand information from S3 (structured)
            game_context: Game information from S3 (structured)
            creative_seed: Optional seed idea to build upon
        
        Returns:
            IdeationResult with the generated idea
        """
        parser = PydanticOutputParser(pydantic_object=IdeationResult)
        
        # Build context strings
        trend_str = ""
        if trend_context and mode in ["trends", "viral"]:
            trend_str = f"<TRENDS>\n{trend_context.to_context_block()}\n</TRENDS>"
        
        # Build brand/game context string
        brand_str = ""
        if mode == "brand":
            if brand_context:
                brand_str = brand_context.to_ideation_context()
            if game_context:
                game_str = game_context.to_ideation_context()
                brand_str = f"{brand_str}\n\n{game_str}" if brand_str else game_str
            
            # Use brand/game audience if not specified
            if not audience:
                if brand_context and brand_context.target_audience:
                    audience = brand_context.target_audience
                elif game_context and game_context.target_audience:
                    audience = game_context.target_audience
        
        seed_str = ""
        if creative_seed:
            seed_str = f"<SEED>\n{creative_seed}\n</SEED>"
        elif mode == "creativity":
            # Pick a random seed for creativity mode
            seed_category = self._map_content_type_to_seed_category(content_type)
            seeds = CREATIVITY_SEEDS.get(seed_category, CREATIVITY_SEEDS["video"])
            seed_str = f"<SEED>\nInspiration: {random.choice(seeds)}\n</SEED>"
        
        audience_str = audience or self._get_default_audience(content_type)
        
        messages = [
            ("system", system_prompt_ideation.format(
                format_instructions=parser.get_format_instructions()
            )),
            ("human", human_prompt_ideation.format(
                mode=mode,
                content_type=content_type,
                audience=audience_str,
                trend_context=trend_str,
                brand_context=brand_str,
                seed_context=seed_str,
            )),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        result = parser.parse(response.content)
        
        # Ensure ideation_mode is set correctly
        result.ideation_mode = mode
        
        return result
    
    async def ideate_for_brand(
        self,
        content_type: str,
        brand_context: Optional[BrandContext] = None,
        game_context: Optional[GameContext] = None,
        trend_context: Optional[TrendContext] = None,
        # Legacy support for dict-based brand_data
        brand_data: Optional[dict] = None,
        characters: Optional[List] = None,
    ) -> IdeationResult:
        """
        Generate idea specifically for a brand/game with its characters.
        
        Args:
            content_type: Type of content
            brand_context: BrandContext object from S3
            game_context: GameContext object from S3
            trend_context: Optional trend data
            brand_data: (Legacy) Brand information dict from S3
            characters: (Legacy) List of brand characters
        
        Returns:
            IdeationResult aligned with brand
        """
        # If structured contexts not provided, build from legacy dict
        if brand_context is None and brand_data:
            from interfaces.entities.brand_context import BrandContext as BC
            char_dicts = []
            if characters:
                for char in characters[:6]:
                    char_dicts.append({
                        "name": getattr(char, 'identifier_in_scene', str(char)),
                        "role": getattr(char, 'role', None),
                        "personality": getattr(char, 'personality', None),
                        "description": getattr(char, 'description', None),
                        "traits": getattr(char, 'traits', None),
                    })
            brand_context = BC.from_s3_data(
                brand_id=brand_data.get('id', 'unknown'),
                brand_data=brand_data,
                characters=char_dicts,
            )
        
        # Determine audience from brand/game context
        audience = None
        if brand_context and brand_context.target_audience:
            audience = brand_context.target_audience
        elif game_context and game_context.target_audience:
            audience = game_context.target_audience
        elif brand_data:
            audience = brand_data.get('target_audience', 'All Ages')
        else:
            audience = 'All Ages'
        
        return await self.ideate(
            content_type=content_type,
            mode="brand",
            audience=audience,
            trend_context=trend_context,
            brand_context=brand_context,
            game_context=game_context,
        )
    
    async def ideate_for_game(
        self,
        content_type: str,
        game_context: GameContext,
        brand_context: Optional[BrandContext] = None,
        trend_context: Optional[TrendContext] = None,
    ) -> IdeationResult:
        """
        Generate idea specifically for a game.
        
        Args:
            content_type: Type of content
            game_context: GameContext object from S3
            brand_context: Optional associated brand context
            trend_context: Optional trend data
        
        Returns:
            IdeationResult aligned with game
        """
        return await self.ideate(
            content_type=content_type,
            mode="brand",
            audience=game_context.target_audience,
            trend_context=trend_context,
            brand_context=brand_context,
            game_context=game_context,
        )
    
    async def ideate_podcast_episode(
        self,
        topic_area: Optional[str] = None,
        trend_context: Optional[TrendContext] = None,
        previous_episodes: Optional[List[str]] = None,
    ) -> PodcastEpisodeIdea:
        """
        Generate a podcast episode idea.
        
        Args:
            topic_area: General topic area to focus on
            trend_context: Current trends
            previous_episodes: List of previous episode titles to avoid repetition
        
        Returns:
            PodcastEpisodeIdea
        """
        parser = PydanticOutputParser(pydantic_object=PodcastEpisodeIdea)
        
        context_parts = []
        if topic_area:
            context_parts.append(f"Focus Area: {topic_area}")
        if trend_context:
            context_parts.append(f"Current Trends:\n{trend_context.to_context_block()}")
        if previous_episodes:
            context_parts.append(f"Previous Episodes (avoid similar topics):\n" + "\n".join(f"- {ep}" for ep in previous_episodes[-5:]))
        
        context = "\n\n".join(context_parts) if context_parts else "Generate a fresh, engaging podcast episode idea."
        
        messages = [
            ("system", f"""You are a podcast content strategist. Generate a compelling podcast episode idea that would engage listeners and translate well to video content.

{parser.get_format_instructions()}"""),
            ("human", context),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return parser.parse(response.content)
    
    async def ideate_series(
        self,
        content_type: str,
        episode_count: int = 5,
        theme: Optional[str] = None,
        brand_context: Optional[str] = None,
        trend_context: Optional[TrendContext] = None,
    ) -> SeriesIdeation:
        """
        Generate ideas for a content series.
        
        Args:
            content_type: Type of content for the series
            episode_count: Number of episodes to ideate
            theme: Overall theme for the series
            brand_context: Brand information if applicable
            trend_context: Current trends
        
        Returns:
            SeriesIdeation with series concept and episode ideas
        """
        parser = PydanticOutputParser(pydantic_object=SeriesIdeation)
        
        context_parts = [f"Content Type: {content_type}", f"Episodes Needed: {episode_count}"]
        if theme:
            context_parts.append(f"Theme: {theme}")
        if brand_context:
            context_parts.append(f"Brand Context:\n{brand_context}")
        if trend_context:
            context_parts.append(f"Current Trends:\n{trend_context.to_context_block()}")
        
        messages = [
            ("system", f"""You are a content series strategist. Generate a cohesive series concept with individual episode ideas that build on each other and keep audiences coming back.

{parser.get_format_instructions()}"""),
            ("human", "\n\n".join(context_parts)),
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return parser.parse(response.content)
    
    def _map_content_type_to_seed_category(self, content_type: str) -> str:
        """Map content type to seed category."""
        mapping = {
            "video": "video",
            "shorts": "shorts",
            "song": "song",
            "lyrics": "song",
            "documentary": "documentary",
            "ad": "ad",
            "podcast": "podcast",
            "kids": "kids",
            "learning": "documentary",
            "movie": "video",
            "short_movie": "video",
            "music_video": "song",
        }
        return mapping.get(content_type, "video")
    
    def _get_default_audience(self, content_type: str) -> str:
        """Get default audience for content type."""
        defaults = {
            "kids": "Children ages 4-10 and their parents",
            "learning": "Students and lifelong learners",
            "shorts": "Gen Z and Millennials on social media",
            "documentary": "Curious adults interested in deep dives",
            "ad": "Target customers of the brand",
            "podcast": "Commuters and multitaskers",
            "song": "Music lovers across all ages",
            "movie": "General audience film enthusiasts",
        }
        return defaults.get(content_type, "General audience")
    
    def get_random_virality_factors(self, count: int = 3) -> List[str]:
        """Get random virality factors for idea enhancement."""
        return random.sample(VIRALITY_FACTORS, min(count, len(VIRALITY_FACTORS)))
