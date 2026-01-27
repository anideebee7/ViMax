"""
Initialization script for IntelliVerse X Brand Ecosystem on S3.

This script pushes the metadata for all 5 flavors (YouTube channels) to S3,
creating a permanent and adaptable context for the Content Planner.
"""
import os
import json
import logging
import subprocess
import tempfile
from pathlib import Path

# Brand Flavor Definitions (Central Truth)
ECOSYSTEM = {
    "brand": {
        "id": "intelli-verse-x",
        "name": "IntelliVerse X",
        "description": "A multi-niche content powerhouse exploring the intersections of tech, gaming, luxury, health, and curiosity.",
        "flavors": ["health", "playx", "luxe", "techx", "autocurio"]
    },
    "flavors": {
        "health": {
            "channel": "IntelliVerse Health",
            "genre": "Wellness & Biohacking",
            "audience": "Health-conscious adults interested in longevity and performance",
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
            "genre": "Gaming & Live Sports",
            "audience": "Gamers, sports fans, and competitive event viewers",
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
            "genre": "Luxury Lifestyle",
            "audience": "High-net-worth individuals, luxury enthusiasts, fashionistas",
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
            "genre": "Future Tech & AI",
            "audience": "Early adopters, developers, AI enthusiasts, tech professionals",
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
            "genre": "Automotive Engineering",
            "audience": "Car enthusiasts, engineering students, DIY mechanics",
            "keywords": [
                "automotive", "cars", "vehicles", "engineering", "how it works", "restoration",
                "electric vehicles", "ev", "tesla", "engine", "mechanic", "diy", "transportation",
                "autonomous driving", "supercars", "classic cars", "racing", "f1", "motorsport",
                "tech in cars", "hydrogen", "sustainable transport", "curiosity", "exploration"
            ],
            "pillars": ["How It Works", "Car Tech", "Restoration/DIY", "Future of Transport", "Curiosity/Exploration"]
        }
    }
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def push_to_s3(local_path, s3_path):
    result = subprocess.run(["aws", "s3", "cp", local_path, s3_path, "--acl", "public-read"], capture_output=True, text=True)
    return result.returncode == 0

def main():
    s3_bucket = "intelli-verse-x-media"
    s3_prefix = "agent-assets"
    brand_id = ECOSYSTEM["brand"]["id"]
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Push main brand.json
        brand_json_path = Path(tmp_dir) / "brand.json"
        with open(brand_json_path, 'w') as f:
            json.dump(ECOSYSTEM["brand"], f, indent=2)
        
        s3_brand_path = f"s3://{s3_bucket}/{s3_prefix}/brands/{brand_id}/brand.json"
        if push_to_s3(str(brand_json_path), s3_brand_path):
            logger.info(f"Pushed brand.json to {s3_brand_path}")
        
        # 2. Push each flavor.json
        for flavor, config in ECOSYSTEM["flavors"].items():
            flavor_dir = Path(tmp_dir) / "flavors" / flavor
            flavor_dir.mkdir(parents=True, exist_ok=True)
            
            flavor_json_path = flavor_dir / "flavor.json"
            with open(flavor_json_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            s3_flavor_path = f"s3://{s3_bucket}/{s3_prefix}/brands/{brand_id}/flavors/{flavor}/flavor.json"
            if push_to_s3(str(flavor_json_path), s3_flavor_path):
                logger.info(f"Pushed {flavor}.json to {s3_flavor_path}")

if __name__ == "__main__":
    main()
