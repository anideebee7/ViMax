from pipelines.base.idea import VideoPipeline
from pipelines.base.script import Script2VideoPipeline
from pipelines.music.song import SongPipeline
from pipelines.content.podcast import Podcast2VideoPipeline
from pipelines.music.lyrics import LyricsPipeline
from pipelines.ads.video import AdPipeline
from pipelines.content.documentary import DocumentaryPipeline
from pipelines.series.learning import LearningSeriesPipeline
from pipelines.music.song_to_video import Song2MusicVideoPipeline
from pipelines.movies.short import ShortMoviePipeline
from pipelines.movies.short_video import ShortMovieVideoPipeline
from pipelines.movies.standard import MoviePipeline
from pipelines.movies.kids import KidsMoviePipeline
from pipelines.ads.banners import AdBannersPipeline
from pipelines.music.video import MusicVideoPipeline
from pipelines.series.podcast import PodcastSeriesPipeline
from pipelines.series.tv import TVSeriesPipeline
from pipelines.series.weekly import WeeklySeriesPipeline
from pipelines.social.shorts import ViralShortsPipeline

# Novel2MoviePipeline requires additional dependencies (langchain embeddings cache)
# Import it conditionally to avoid breaking other pipelines
try:
    from pipelines.movies.novel import Novel2MoviePipeline
    _HAS_NOVEL2MOVIE = True
except ImportError:
    Novel2MoviePipeline = None
    _HAS_NOVEL2MOVIE = False

__all__ = [
    "VideoPipeline",
    "Script2VideoPipeline",
    "SongPipeline",
    "Podcast2VideoPipeline",
    "LyricsPipeline",
    "AdPipeline",
    "DocumentaryPipeline",
    "LearningSeriesPipeline",
    "Song2MusicVideoPipeline",
    "ShortMoviePipeline",
    "ShortMovieVideoPipeline",
    "MoviePipeline",
    "KidsMoviePipeline",
    "AdBannersPipeline",
    "MusicVideoPipeline",
    "PodcastSeriesPipeline",
    "TVSeriesPipeline",
    "WeeklySeriesPipeline",
    "ViralShortsPipeline",
]

if _HAS_NOVEL2MOVIE:
    __all__.append("Novel2MoviePipeline")
