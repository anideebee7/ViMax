"""
Content Planner Agent for Multi-Flavor Brand Planning.

This agent:
1. Normalizes data from multiple sources (Google Trends, YouTube, NewsAPI, Reddit)
2. Filters based on brand "flavors" (niches like Health, Gaming, Luxe, Tech, AutoCurio)
3. Clusters and deduplicates topics
4. Scores topics based on brand fit and trending velocity
5. Generates weekly calendar (Shorts/day + Long-form topics)
6. Pushes/Loads profiling data to/from S3
"""
import logging
import json
import os
import re
import subprocess
import tempfile
from typing import List, Dict, Set, Optional, Any, Literal
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

from utils.pipeline.s3_loader import S3CharacterLoader

# Brand Flavor Defaults (Fallback if S3 is empty)
FLAVORS = {
    "health": {
        "channel": "IntelliVerse Health",
        "keywords": [
            "health", "wellness", "nutrition", "diet", "protein", "fiber", "sugar", "carb", "keto",
            "fasting", "intermittent", "weight", "fat loss", "obesity", "metabolism", "insulin",
            "diabetes", "blood sugar", "cholesterol", "bp", "blood pressure",
            "sleep", "cortisol", "stress", "anxiety", "gut", "microbiome", "probiotic", "prebiotic",
            "exercise", "walking", "workout", "fitness", "hiit", "strength",
            "supplement", "vitamin", "magnesium", "creatine", "omega", "zinc",
            "longevity", "aging", "inflammation", "heart", "cardio"
        ],
        "pillars": ["Metabolism/Weight Loss", "Sleep/Stress", "Gut/Nutrition", "Supplements", "Daily Habits"]
    },
    "playx": {
        "channel": "IntelliVerse PlayX",
        "keywords": [
            "gaming", "gameplay", "ps5", "xbox", "nintendo", "pc gaming", "esports", "streaming",
            "twitch", "multiplayer", "co-op", "indie games", "rpg", "fps", "battle royale",
            "walkthrough", "speedrun", "modding", "gaming hardware", "gpu", "steam deck",
            "metaverse", "vr gaming", "ar gaming", "casual games", "mobile gaming", "roblox", "minecraft",
            "sports", "live sports", "baseball", "football", "cricket", "golf", "sporting events",
            "nfl", "nba", "mlb", "premier league", "champions league", "world cup"
        ],
        "pillars": ["Game Highlights", "Live Sports/Events", "Gaming News", "Hardware Reviews", "Tutorials/Hacks"]
    },
    "luxe": {
        "channel": "IntelliVerse Luxe",
        "keywords": [
            "luxury", "premium", "lifestyle", "fashion", "high-end", "travel", "exclusive",
            "watches", "jewelry", "designer", "couture", "supercars", "yachts", "private jets",
            "real estate", "fine dining", "michelin star", "hotels", "resorts", "skincare",
            "wellness", "investment", "collectibles", "art", "auctions"
        ],
        "pillars": ["Luxury Lifestyle", "Fashion/Style", "Travel/Excursions", "Premium Products", "Exclusives"]
    },
    "techx": {
        "channel": "IntelliVerse TechX",
        "keywords": [
            "technology", "tech news", "ai", "artificial intelligence", "chatgpt", "llm", "gadgets",
            "iphone", "android", "silicon valley", "startups", "coding", "software", "developer",
            "future tech", "robotics", "automation", "cybersecurity", "web3", "crypto", "blockchain",
            "space tech", "energy", "batteries", "ev", "autonomous"
        ],
        "pillars": ["Tech News", "AI/Innovation", "Gadget Reviews", "Software/Dev", "Future Trends"]
    },
    "autocurio": {
        "channel": "AutoCurio",
        "keywords": [
            "automotive", "cars", "vehicles", "engineering", "how it works", "restoration",
            "electric vehicles", "ev", "tesla", "engine", "mechanic", "diy", "transportation",
            "autonomous driving", "supercars", "classic cars", "racing", "f1", "motorsport",
            "tech in cars", "hydrogen", "sustainable transport", "curiosity", "exploration"
        ],
        "pillars": ["How It Works", "Car Tech", "Restoration/DIY", "Future of Transport", "Curiosity/Exploration"]
    }
}

class ContentPlanner:
    """Plans weekly content calendar based on trending topics for specific brand flavors."""

    def __init__(self, flavor: str = "health", brand_id: str = "intelli-verse-x", use_s3_config: bool = True):
        """Initialize the Content Planner.
        
        Args:
            flavor: The niche flavor (health, playx, luxe, techx, autocurio)
            brand_id: The root brand ID on S3
            use_s3_config: If True, attempts to load config from S3 ecosystem data
        """
        self.flavor = flavor.lower()
        self.brand_id = brand_id
        self.s3_loader = S3CharacterLoader()
        
        # 1. Start with Hardcoded Fallbacks
        if self.flavor not in FLAVORS:
            logger.warning(f"Flavor {flavor} not found in defaults, defaulting to health")
            self.flavor = "health"
        self.config = FLAVORS[self.flavor]
        
        # 2. Try to Load from S3 for adaptivity
        if use_s3_config:
            try:
                ecosystem = self.s3_loader.load_brand_ecosystem(self.brand_id)
                if self.flavor in ecosystem["flavors"]:
                    self.config = ecosystem["flavors"][self.flavor]
                    logger.info(f"Loaded {self.flavor} configuration from S3 permanent context")
            except Exception as e:
                logger.warning(f"Could not load S3 permanent context for {self.brand_id}/{self.flavor}: {e}")
        
        # S3 Settings for saving plans
        self.s3_bucket = self.s3_loader.config.bucket
        self.s3_prefix = self.s3_loader.config.prefix

    def clean_topic(self, text: str) -> str:
        """Clean and normalize topic text."""
        if not text:
            return ""
        cleaned = text.lower()
        cleaned = re.sub(r'\([^)]*\)', '', cleaned)
        cleaned = re.sub(r'[^a-z0-9\s]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

    def is_brand_topic(self, topic: str) -> bool:
        """Check if a topic is related to the current brand flavor."""
        topic_lower = topic.lower()
        return any(keyword in topic_lower for keyword in self.config["keywords"])

    def recency_bonus(self, timestamp_ms: float) -> float:
        """Calculate recency bonus score (0-15)."""
        now_ms = datetime.now().timestamp() * 1000
        hours_ago = (now_ms - timestamp_ms) / 3600000
        
        if hours_ago <= 2: return 15
        elif hours_ago <= 6: return 10
        elif hours_ago <= 24: return 5
        else: return 0

    def format_fit(self, topic: str) -> Dict[str, float]:
        """Determine format fit (short vs long-form)."""
        topic_lower = topic.lower()
        short_indicators = re.search(r'(mistake|myth|hack|best time|stop|do this|avoid|secret|teaser|highlight)', topic_lower)
        long_indicators = re.search(r'(explained|science|study|research|how to|guide|complete|documentary|review)', topic_lower)
        
        if short_indicators and long_indicators: return {'short': 15, 'long': 15, 'both': 30}
        elif short_indicators: return {'short': 15, 'long': 0, 'both': 15}
        elif long_indicators: return {'short': 0, 'long': 15, 'both': 15}
        else: return {'short': 10, 'long': 10, 'both': 20}

    def velocity_type(self, topic: str) -> Dict[str, any]:
        """Determine velocity type (spike/wave/evergreen)."""
        topic_lower = topic.lower()
        if re.search(r'(fda|recall|outbreak|breaking|hospital|warning|launch|leak|exclusive)', topic_lower):
            return {'type': 'spike', 'bonus': 5}
        elif re.search(r'(new study|research|trial|report|review|unboxing)', topic_lower):
            return {'type': 'wave', 'bonus': 10}
        else:
            return {'type': 'evergreen', 'bonus': 20}

    def source_base_score(self, source: str) -> float:
        """Get base score for a source."""
        scores = {'google': 45, 'youtube': 30, 'news': 30, 'reddit': 20}
        return scores.get(source, 0)

    def consensus_bonus(self, source_count: int) -> float:
        """Calculate consensus bonus based on number of sources."""
        if source_count >= 4: return 75
        elif source_count == 3: return 45
        elif source_count == 2: return 20
        else: return 0

    def pillar_for_topic(self, topic: str) -> str:
        """Assign a content pillar to a topic based on flavor configuration."""
        pillars = self.config["pillars"]
        topic_lower = topic.lower()
        
        # Simple heuristic mapping for each flavor
        if self.flavor == "health":
            if re.search(r'(metab|weight|fat|insulin)', topic_lower): return pillars[0]
            if re.search(r'(sleep|cortisol|stress)', topic_lower): return pillars[1]
            if re.search(r'(gut|microbi|fiber)', topic_lower): return pillars[2]
            if re.search(r'(supplement|vitamin)', topic_lower): return pillars[3]
            return pillars[4]
        elif self.flavor == "playx":
            if re.search(r'(highlight|clip|pro player)', topic_lower): return pillars[0]
            if re.search(r'(news|leak|release)', topic_lower): return pillars[1]
            if re.search(r'(gpu|console|hardware)', topic_lower): return pillars[2]
            if re.search(r'(tutorial|hack|guide)', topic_lower): return pillars[3]
            return pillars[4]
        elif self.flavor == "techx":
            if re.search(r'(news|breaking|event)', topic_lower): return pillars[0]
            if re.search(r'(ai|gpt|robot|future)', topic_lower): return pillars[1]
            if re.search(r'(review|iphone|unboxing)', topic_lower): return pillars[2]
            if re.search(r'(code|software|dev)', topic_lower): return pillars[3]
            return pillars[4]
        elif self.flavor == "autocurio":
            if re.search(r'(how|science|engine)', topic_lower): return pillars[0]
            if re.search(r'(tech|ev|autonomous)', topic_lower): return pillars[1]
            if re.search(r'(diy|restore|fix)', topic_lower): return pillars[2]
            if re.search(r'(future|flying|sustainable)', topic_lower): return pillars[3]
            return pillars[4]
        
        # Default: pick first pillar
        return pillars[0]

    def normalize_items(
        self,
        google_trends: List[Dict],
        youtube_items: List[Dict],
        newsapi_items: List[Dict],
        reddit_items: List[Dict]
    ) -> List[Dict]:
        """Normalize items from all sources into a common format."""
        normalized = []
        
        for item in google_trends:
            pub_date = item.get('pubDate')
            ts = datetime.now().timestamp() * 1000
            if pub_date:
                for fmt in ('%a, %d %b %Y %H:%M:%S %Z', '%a, %d %b %Y %H:%M:%S %z'):
                    try:
                        ts = datetime.strptime(pub_date, fmt).timestamp() * 1000
                        break
                    except: continue
            
            normalized.append({
                'source': 'google',
                'topicRaw': item.get('title', ''),
                'topic': self.clean_topic(item.get('title', '')),
                'url': item.get('link', ''),
                'ts': ts,
                'metrics': {'rank': 0}
            })
        
        for item in youtube_items:
            snippet = item.get('snippet', {})
            stats = item.get('statistics', {})
            published_at = snippet.get('publishedAt', '')
            ts = datetime.now().timestamp() * 1000
            if published_at:
                try: ts = datetime.fromisoformat(published_at.replace('Z', '+00:00')).timestamp() * 1000
                except: pass
            
            normalized.append({
                'source': 'youtube',
                'topicRaw': snippet.get('title', ''),
                'topic': self.clean_topic(snippet.get('title', '')),
                'url': f"https://www.youtube.com/watch?v={item.get('id', '')}",
                'ts': ts,
                'metrics': {'views': int(stats.get('viewCount', 0) or 0)}
            })
        
        for item in newsapi_items:
            published_at = item.get('publishedAt', '')
            ts = datetime.now().timestamp() * 1000
            if published_at:
                try: ts = datetime.fromisoformat(published_at.replace('Z', '+00:00')).timestamp() * 1000
                except: pass
            
            normalized.append({
                'source': 'news',
                'topicRaw': item.get('title', ''),
                'topic': self.clean_topic(item.get('title', '')),
                'url': item.get('url', ''),
                'ts': ts,
                'metrics': {'source': item.get('source', {}).get('name', '')}
            })
        
        for item in reddit_items:
            created_utc = item.get('created_utc', 0)
            ts = created_utc * 1000 if created_utc else datetime.now().timestamp() * 1000
            
            normalized.append({
                'source': 'reddit',
                'topicRaw': item.get('title', ''),
                'topic': self.clean_topic(item.get('title', '')),
                'url': item.get('url', ''),
                'ts': ts,
                'metrics': {'upvotes': int(item.get('ups', 0) or 0), 'subreddit': item.get('subreddit', '')}
            })
        
        return normalized

    def cluster_and_score(self, normalized_items: List[Dict]) -> List[Dict]:
        """Cluster topics, deduplicate, and score them for the current flavor."""
        # Filter to flavor-related topics
        brand_items = [item for item in normalized_items if item['topic'] and self.is_brand_topic(item['topic'])]
        logger.info(f"Filtered to {len(brand_items)} {self.flavor}-related items from {len(normalized_items)} total")
        
        groups = {}
        for item in brand_items:
            topic = item['topic']
            if not topic: continue
            
            if topic not in groups:
                groups[topic] = {
                    'topic': topic,
                    'displayTitle': item['topicRaw'],
                    'sources': set(),
                    'urls': [],
                    'newestTs': item['ts'],
                    'metricsAgg': {'views': 0, 'upvotes': 0, 'newsCount': 0}
                }
            
            group = groups[topic]
            group['sources'].add(item['source'])
            group['urls'].append({
                'source': item['source'], 'url': item['url'], 'title': item['topicRaw'], 'ts': item['ts']
            })
            group['newestTs'] = max(group['newestTs'], item['ts'])
            
            if item['source'] == 'youtube': group['metricsAgg']['views'] += item['metrics'].get('views', 0)
            elif item['source'] == 'reddit': group['metricsAgg']['upvotes'] += item['metrics'].get('upvotes', 0)
            elif item['source'] == 'news': group['metricsAgg']['newsCount'] += 1
        
        scored = []
        for topic, group in groups.items():
            sources = list(group['sources'])
            score = sum(self.source_base_score(s) for s in sources)
            score += self.consensus_bonus(len(sources))
            score += self.recency_bonus(group['newestTs'])
            score += self.format_fit(topic)['both']
            vt = self.velocity_type(topic)
            score += vt['bonus']
            score += 25 # Flavor fit bonus
            
            scored.append({
                'topic': topic,
                'displayTitle': group['displayTitle'],
                'sources': sources,
                'newestTs': group['newestTs'],
                'score': score,
                'velocity': vt['type'],
                'urls': group['urls'][:6],
                'metrics': group['metricsAgg'],
                'pillar': self.pillar_for_topic(topic)
            })
        
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored

    def plan_weekly_content(
        self,
        google_trends: List[Dict],
        youtube_items: List[Dict],
        newsapi_items: List[Dict],
        reddit_items: List[Dict],
        top_n: int = 10
    ) -> Dict:
        """Generate full weekly plan."""
        normalized = self.normalize_items(google_trends, youtube_items, newsapi_items, reddit_items)
        scored = self.cluster_and_score(normalized)
        top_clusters = scored[:top_n]
        
        # Generate calendar
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        calendar = []
        for idx in range(7):
            cluster_a = top_clusters[(idx * 2) % len(top_clusters)] if top_clusters else None
            cluster_b = top_clusters[(idx * 2 + 1) % len(top_clusters)] if len(top_clusters) > 1 else cluster_a
            
            shorts = []
            if cluster_a:
                shorts.append({
                    'topic': cluster_a['topic'],
                    'hook': f"Why you should care about {cluster_a['topic']} right now",
                    'pillar': cluster_a['pillar']
                })
            if cluster_b:
                shorts.append({
                    'topic': cluster_b['topic'],
                    'hook': f"The truth about {cluster_b['topic']}",
                    'pillar': cluster_b['pillar']
                })
            
            calendar.append({'day': days[idx], 'shorts': shorts})
            
        long_form = []
        for candidate in top_clusters[:2]:
            long_form.append({
                'title': f"Deep Dive: {candidate['displayTitle']}",
                'topic': candidate['topic'],
                'pillar': candidate['pillar']
            })
            
        result = {
            'generatedAt': datetime.now().isoformat(),
            'flavor': self.flavor,
            'channel': self.config['channel'],
            'topClusters': top_clusters,
            'longForm': long_form,
            'calendar7Days': calendar
        }
        return result

    def push_plan_to_s3(self, plan: Dict) -> bool:
        """Push the weekly plan to S3 for permanent profiling."""
        s3_path = f"s3://{self.s3_bucket}/{self.s3_prefix}/brands/{self.brand_id}/flavors/{self.flavor}/weekly_plans/plan_{datetime.now().strftime('%Y%W')}.json"
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
            json.dump(plan, f, indent=2)
            temp_path = f.name
            
        try:
            result = subprocess.run(["aws", "s3", "cp", temp_path, s3_path, "--acl", "public-read"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Successfully pushed plan to S3: {s3_path}")
                return True
            else:
                logger.error(f"Failed to push plan to S3: {result.stderr}")
                return False
        finally:
            if os.path.exists(temp_path): os.unlink(temp_path)

    def load_profile_from_s3(self) -> Optional[Dict]:
        """Load brand profile data from S3 if it exists."""
        s3_path = f"s3://{self.s3_bucket}/{self.s3_prefix}/brands/{self.brand_id}/flavors/{self.flavor}/profile.json"
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name
            
        try:
            result = subprocess.run(["aws", "s3", "cp", s3_path, temp_path], capture_output=True, text=True)
            if result.returncode == 0:
                with open(temp_path, 'r') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logger.warning(f"Error loading profile from S3: {e}")
            return None
        finally:
            if os.path.exists(temp_path): os.unlink(temp_path)
