"""
Smoke-test the Brand/Game/Character API without external services.

This script monkeypatches API dependencies to use an in-memory/local
storage and fake generators so we can validate endpoint wiring.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from api import main as api_main


class FakeConfig:
    """Minimal config stand-in."""

    def __init__(self) -> None:
        self.xai_api_key = "fake"
        self.xai_base_url = "https://example.invalid"
        self.xai_model = "fake-model"
        self.piapi_api_key = "fake"
        self.s3_bucket = "local-bucket"
        self.s3_prefix = "agent-assets"
        self.s3_region = "local"

    @classmethod
    def from_env(cls) -> "FakeConfig":
        return cls()


class FakeStorage:
    """Local filesystem storage used in tests."""

    root_dir: Optional[str] = None

    def __init__(self, config: FakeConfig) -> None:
        if FakeStorage.root_dir is None:
            FakeStorage.root_dir = tempfile.mkdtemp(prefix="vimax_api_smoke_")
        self.root_dir = FakeStorage.root_dir
        self.bucket = config.s3_bucket
        self.prefix = config.s3_prefix
        self.region = config.s3_region

    def _path(self, s3_key: str, filename: Optional[str] = None) -> str:
        base = os.path.join(self.root_dir, s3_key)
        return os.path.join(base, filename) if filename else base

    def list_items(self, s3_key: str) -> List[str]:
        path = self._path(s3_key)
        if not os.path.isdir(path):
            return []
        items: List[str] = []
        for name in os.listdir(path):
            if name.endswith(".json"):
                continue
            items.append(name)
        return items

    async def save_json(self, s3_key: str, filename: str, data: Dict[str, Any], public: bool = True) -> str:
        os.makedirs(self._path(s3_key), exist_ok=True)
        path = self._path(s3_key, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return f"file://{path}"

    async def load_json(self, s3_key: str, filename: str) -> Optional[Dict[str, Any]]:
        path = self._path(s3_key, filename)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def download_and_upload(self, source_url: str, s3_key: str, filename: str, public: bool = True) -> str:
        os.makedirs(self._path(s3_key), exist_ok=True)
        path = self._path(s3_key, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"placeholder for {source_url}\n")
        return f"file://{path}"

    async def update_characters_mapping(
        self,
        asset_type: str,
        asset_id: str,
        char_id: str,
        char_name: str,
        aliases: Optional[List[str]] = None,
    ) -> None:
        mapping_key = f"{asset_type}/{asset_id}/Characters"
        mapping = await self.load_json(mapping_key, "characters_mapping.json") or {
            "description": "Maps character IDs and aliases to canonical names",
            "mapping": {},
            "characters": {},
        }
        mapping["mapping"][char_id] = char_name
        for alias in aliases or []:
            mapping["mapping"][alias] = char_name
        mapping["characters"][char_name] = {
            "id": char_id,
            "name": char_name,
            "folder": f"Characters/{char_name}/",
        }
        await self.save_json(mapping_key, "characters_mapping.json", mapping)

    async def update_asset_characters_list(self, asset_type: str, asset_id: str, char_name: str) -> None:
        filename = "brand.json" if asset_type == "brands" else "game.json"
        data = await self.load_json(f"{asset_type}/{asset_id}", filename) or {}
        data.setdefault("characters", [])
        if char_name not in data["characters"]:
            data["characters"].append(char_name)
        await self.save_json(f"{asset_type}/{asset_id}", filename, data)


class FakeConceptGenerator:
    """Return deterministic concept data without external calls."""

    def __init__(self, config: FakeConfig) -> None:
        self.config = config

    async def generate_brand_concept(self, prompt: str, industry: Optional[str] = None, style: Optional[str] = None) -> Dict[str, Any]:
        return {
            "name": "Test Brand",
            "tagline": "Test tagline",
            "description": "Test brand description.",
            "story": "Test brand story.",
            "values": ["quality", "curiosity"],
            "target_audience": "Test audience",
            "visual_style": "Playful",
            "color_palette": ["#ff0000", "#00ff00"],
            "personality_traits": ["bold", "friendly"],
            "suggested_characters": [
                {"name": "TestHero", "role": "hero", "personality": "Brave", "appearance": "Red armor"}
            ],
        }

    async def generate_game_concept(
        self,
        prompt: str,
        genre: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        brand_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "name": "Test Game",
            "tagline": "Play to win",
            "description": "Test game description.",
            "genre": genre or "puzzle",
            "story": "Test game story.",
            "mechanics": "Match tiles",
            "target_audience": "Everyone",
            "unique_features": ["fast rounds"],
            "visual_style": "Cartoon",
            "suggested_characters": [
                {
                    "name": "TestBuddy",
                    "role": "supporting",
                    "personality": "Cheerful",
                    "appearance": "Blue hoodie",
                    "abilities": "Speed",
                    "backstory": "From the test lab",
                }
            ],
        }

    async def generate_character_concept(
        self,
        prompt: str,
        style: Optional[str] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "name": "Generated Character",
            "identifier_in_scene": "generated_character",
            "role": "support",
            "personality": "Helpful",
            "appearance": {"overview": "Green outfit"},
            "static_features": "Green outfit, bright eyes",
            "dynamic_features": "Smiles often",
            "backstory": "Created for testing.",
        }


class FakeMediaGenerator:
    """Return placeholder URLs for media generation."""

    def __init__(self, config: FakeConfig) -> None:
        self.config = config

    async def generate_character_portrait(self, description: str, style: str = "3D animated cartoon style") -> str:
        return "https://example.com/portrait_front.png"

    async def generate_side_portrait(self, front_image_url: str, character_name: str) -> str:
        return "https://example.com/portrait_side.png"

    async def generate_back_portrait(self, front_image_url: str, character_name: str) -> str:
        return "https://example.com/portrait_back.png"

    async def generate_voice_sample(self, text: str, reference_audio_url: Optional[str] = None) -> str:
        return "https://example.com/voice.m4a"

    async def generate_logo(self, brand_name: str, description: str, style: str = "modern minimalist") -> str:
        return "https://example.com/logo.png"


def _patch_api_dependencies() -> None:
    api_main.GeneratorConfig = FakeConfig
    api_main.S3Storage = FakeStorage
    api_main.ConceptGenerator = FakeConceptGenerator
    api_main.MediaGenerator = FakeMediaGenerator


def _poll_task(client: TestClient, task_id: str, timeout_seconds: int = 5) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        resp = client.get(f"/tasks/{task_id}")
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.1)
    return payload


def main() -> None:
    _patch_api_dependencies()
    with TestClient(api_main.app) as client:
        results: Dict[str, Any] = {}

        results["health"] = client.get("/health").json()

        brand_resp = client.post(
            "/brands",
            json={
                "name": "Test Brand",
                "description": "Manual brand description",
                "tagline": "Manual tagline",
                "story": "Manual story",
                "values": ["curiosity"],
                "target_audience": "Testers",
                "visual_style": "Playful",
            },
        )
        brand_resp.raise_for_status()
        brand = brand_resp.json()
        results["brand_create"] = brand

        game_resp = client.post(
            "/games",
            json={
                "name": "Test Game",
                "description": "Manual game description",
                "genre": "puzzle",
                "brand_id": brand["id"],
                "platforms": ["android"],
            },
        )
        game_resp.raise_for_status()
        game = game_resp.json()
        results["game_create"] = game

        brand_char_resp = client.post(
            f"/brands/{brand['id']}/characters?generate_images=false&generate_voice=false",
            json={
                "name": "Manual Char",
                "identifier_in_scene": "manual_char",
                "static_features": "Red shirt",
                "dynamic_features": "Waves",
                "backstory": "Manual backstory",
                "personality": "Friendly",
                "role": "support",
            },
        )
        brand_char_resp.raise_for_status()
        brand_char_task = brand_char_resp.json()
        results["brand_character_task"] = _poll_task(client, brand_char_task["task_id"])

        game_char_resp = client.post(
            f"/games/{game['id']}/characters?generate_images=false&generate_voice=false",
            json={
                "name": "Manual Game Char",
                "identifier_in_scene": "manual_game_char",
                "static_features": "Blue jacket",
                "dynamic_features": "Jumps",
                "backstory": "Game backstory",
                "personality": "Curious",
                "role": "hero",
            },
        )
        game_char_resp.raise_for_status()
        game_char_task = game_char_resp.json()
        results["game_character_task"] = _poll_task(client, game_char_task["task_id"])

        gen_brand_resp = client.post(
            "/brands/generate",
            json={"prompt": "A test brand", "generate_logo": True, "num_characters": 1},
        )
        gen_brand_resp.raise_for_status()
        results["brand_generate_task"] = _poll_task(client, gen_brand_resp.json()["task_id"])

        gen_game_resp = client.post(
            "/games/generate",
            json={"prompt": "A test game", "generate_icon": True, "num_characters": 1},
        )
        gen_game_resp.raise_for_status()
        results["game_generate_task"] = _poll_task(client, gen_game_resp.json()["task_id"])

        gen_brand_char_resp = client.post(
            f"/brands/{brand['id']}/characters/generate",
            json={"prompt": "A brave sidekick", "generate_images": True, "generate_voice": False},
        )
        gen_brand_char_resp.raise_for_status()
        results["brand_character_generate_task"] = _poll_task(client, gen_brand_char_resp.json()["task_id"])

        gen_game_char_resp = client.post(
            f"/games/{game['id']}/characters/generate",
            json={"prompt": "A playful rival", "generate_images": False, "generate_voice": False},
        )
        gen_game_char_resp.raise_for_status()
        results["game_character_generate_task"] = _poll_task(client, gen_game_char_resp.json()["task_id"])

        results["brand_list"] = client.get("/brands").json()
        results["game_list"] = client.get("/games").json()
        results["brand_char_list"] = client.get(f"/brands/{brand['id']}/characters").json()
        results["game_char_list"] = client.get(f"/games/{game['id']}/characters").json()

        print("API smoke test results:")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
