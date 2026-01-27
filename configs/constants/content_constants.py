"""
Content constants for pipelines: genres, formats, audience, and runtime limits.

Use these for validation, docstrings, and to ensure consistent support across
pipelines for: normal/animated movies, shorts, short movies, documentaries,
music videos, kids animated music videos, trends toggle, and audience targeting.
"""

from typing import List, Optional

# -----------------------------------------------------------------------------
# Content format: live-action vs animated (for movies, short movies, videos)
# -----------------------------------------------------------------------------

CONTENT_FORMAT_LIVE_ACTION = "live_action"
CONTENT_FORMAT_ANIMATED = "animated"
CONTENT_FORMAT_HYBRID = "hybrid"  # e.g. documentary with animated segments

CONTENT_FORMATS: List[str] = [
    CONTENT_FORMAT_LIVE_ACTION,
    CONTENT_FORMAT_ANIMATED,
    CONTENT_FORMAT_HYBRID,
]

# -----------------------------------------------------------------------------
# Genres supported by screenwriters (movie, short movie, video, documentary, etc.)
# -----------------------------------------------------------------------------

GENRES: List[str] = [
    "drama",
    "comedy",
    "thriller",
    "action",
    "sci-fi",
    "horror",
    "romance",
    "fantasy",
    "mystery",
    "adventure",
    "animation",
    "documentary",
    "musical",
    "western",
    "noir",
    "family",
    "historical",
    "war",
    "crime",
    "superhero",
    "romantic comedy",
    "dark comedy",
    "psychological thriller",
    "slice of life",
    "educational",
]

# -----------------------------------------------------------------------------
# Audience types for content targeting (MPAA-style and age groups)
# -----------------------------------------------------------------------------

AUDIENCE_G = "G"
AUDIENCE_PG = "PG"
AUDIENCE_PG13 = "PG-13"
AUDIENCE_R = "R"
AUDIENCE_NC17 = "NC-17"

AUDIENCE_AGE_KIDS_3_5 = "kids 3-5"
AUDIENCE_AGE_KIDS_6_8 = "kids 6-8"
AUDIENCE_AGE_KIDS_9_12 = "kids 9-12"
AUDIENCE_TEENS = "teens"
AUDIENCE_YOUNG_ADULT = "young adult"
AUDIENCE_ADULTS = "adults"
AUDIENCE_FAMILY = "family"
AUDIENCE_GENERAL = "general"

AUDIENCE_TYPES: List[str] = [
    AUDIENCE_G,
    AUDIENCE_PG,
    AUDIENCE_PG13,
    AUDIENCE_R,
    AUDIENCE_NC17,
    AUDIENCE_AGE_KIDS_3_5,
    AUDIENCE_AGE_KIDS_6_8,
    AUDIENCE_AGE_KIDS_9_12,
    AUDIENCE_TEENS,
    AUDIENCE_YOUNG_ADULT,
    AUDIENCE_ADULTS,
    AUDIENCE_FAMILY,
    AUDIENCE_GENERAL,
]

# -----------------------------------------------------------------------------
# Runtime limits (minutes)
# -----------------------------------------------------------------------------

MOVIE_RUNTIME_MIN_MINUTES = 60
MOVIE_RUNTIME_MAX_MINUTES = 200
SHORT_MOVIE_DURATION_MIN_MINUTES = 5
SHORT_MOVIE_DURATION_MAX_MINUTES = 20
DOCUMENTARY_DURATION_MIN_MINUTES = 10
DOCUMENTARY_DURATION_MAX_MINUTES = 60

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def clamp_runtime(
    value: int,
    min_minutes: int = MOVIE_RUNTIME_MIN_MINUTES,
    max_minutes: int = MOVIE_RUNTIME_MAX_MINUTES,
) -> int:
    """Clamp runtime to allowed range."""
    return max(min_minutes, min(max_minutes, value))


def is_kids_audience(audience: Optional[str]) -> bool:
    """True if audience indicates kids/children/family (e.g. for kids-animated music video)."""
    if not audience:
        return False
    a = audience.lower()
    return any(
        k in a
        for k in ("kids", "children", "child", "family", "3-5", "6-8", "9-12", "g-rated", "g rated")
    )
