"""
AI-powered generators for brands, games, and characters
Uses xAI/OpenRouter for concept generation and PiAPI for media generation
"""
import asyncio
import json
import os
import subprocess
import tempfile
import uuid
from typing import Any, Dict, List, Optional, Tuple
import aiohttp
import boto3
from dataclasses import dataclass


@dataclass
class GeneratorConfig:
    """Configuration for AI generators"""
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-3-beta"
    piapi_api_key: str = ""
    s3_bucket: str = "intelli-verse-x-media"
    s3_prefix: str = "agent-assets"
    s3_region: str = "us-east-1"
    
    @classmethod
    def from_env(cls) -> "GeneratorConfig":
        return cls(
            xai_api_key=os.getenv("XAI_API_KEY", ""),
            xai_base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"),
            xai_model=os.getenv("XAI_MODEL", "grok-2-latest"),
            piapi_api_key=os.getenv("PIAPI_API_KEY", ""),
            s3_bucket=os.getenv("AWS_S3_BUCKET_NAME", "intelli-verse-x-media"),
            s3_prefix=os.getenv("S3_ASSET_PREFIX", "agent-assets"),
            s3_region=os.getenv("AWS_REGION", "us-east-1"),
        )
    
    @property
    def s3_base_url(self) -> str:
        """Get the S3 public URL base"""
        return f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com/{self.s3_prefix}"


class ConceptGenerator:
    """Generates brand/game/character concepts using xAI"""
    
    def __init__(self, config: GeneratorConfig):
        self.config = config
    
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call xAI LLM for generation"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.config.xai_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.config.xai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.config.xai_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 4000
                }
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"LLM call failed: {resp.status} - {error}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    
    async def generate_brand_concept(
        self,
        prompt: str,
        industry: Optional[str] = None,
        style: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a complete brand concept from a prompt"""
        system_prompt = """You are a creative brand strategist and storyteller. 
Generate comprehensive brand concepts that are unique, memorable, and marketable.
Always respond with valid JSON only, no markdown formatting."""
        
        user_prompt = f"""Create a complete brand concept based on this idea:

PROMPT: {prompt}
{f"INDUSTRY: {industry}" if industry else ""}
{f"STYLE PREFERENCE: {style}" if style else ""}

Generate a JSON response with this exact structure:
{{
    "name": "Brand Name",
    "tagline": "Catchy tagline",
    "description": "2-3 sentence description",
    "story": "Brand origin story and narrative (3-4 paragraphs)",
    "values": ["value1", "value2", "value3"],
    "target_audience": "Description of target audience",
    "visual_style": "Description of visual/artistic style",
    "color_palette": ["#hex1", "#hex2", "#hex3"],
    "personality_traits": ["trait1", "trait2", "trait3"],
    "suggested_characters": [
        {{
            "name": "Character Name",
            "role": "Role in brand",
            "personality": "Brief personality description",
            "appearance": "Visual description"
        }}
    ]
}}"""
        
        response = await self._call_llm(system_prompt, user_prompt)
        # Clean up response - remove markdown if present
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()
        
        return json.loads(response)
    
    async def generate_game_concept(
        self,
        prompt: str,
        genre: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        brand_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a complete game concept from a prompt"""
        system_prompt = """You are a creative game designer and storyteller.
Generate engaging game concepts with compelling narratives and characters.
Always respond with valid JSON only, no markdown formatting."""
        
        user_prompt = f"""Create a complete game concept based on this idea:

PROMPT: {prompt}
{f"GENRE: {genre}" if genre else ""}
{f"PLATFORMS: {', '.join(platforms)}" if platforms else ""}
{f"BRAND CONTEXT: {brand_context}" if brand_context else ""}

Generate a JSON response with this exact structure:
{{
    "name": "Game Name",
    "tagline": "Catchy tagline",
    "description": "2-3 sentence elevator pitch",
    "genre": "Game genre",
    "story": "Game narrative and world (3-4 paragraphs)",
    "mechanics": "Core gameplay mechanics description",
    "target_audience": "Target player description",
    "unique_features": ["feature1", "feature2", "feature3"],
    "visual_style": "Art style description",
    "suggested_characters": [
        {{
            "name": "Character Name",
            "role": "protagonist/antagonist/supporting",
            "personality": "Personality traits",
            "appearance": "Detailed visual description",
            "abilities": "Special abilities or traits",
            "backstory": "Character backstory"
        }}
    ]
}}"""
        
        response = await self._call_llm(system_prompt, user_prompt)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()
        
        return json.loads(response)
    
    async def generate_character_concept(
        self,
        prompt: str,
        style: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a character concept from a prompt"""
        system_prompt = """You are a creative character designer.
Create memorable, unique characters with rich backstories.
Always respond with valid JSON only, no markdown formatting."""
        
        user_prompt = f"""Create a detailed character based on this description:

PROMPT: {prompt}
{f"VISUAL STYLE: {style}" if style else ""}
{f"CONTEXT: {context}" if context else ""}

Generate a JSON response with this exact structure:
{{
    "name": "Character Name",
    "identifier_in_scene": "short_identifier",
    "role": "Character's role",
    "personality": "Detailed personality description",
    "appearance": {{
        "overview": "General appearance description",
        "height": "tall/medium/short",
        "build": "body type",
        "distinctive_features": ["feature1", "feature2"],
        "clothing_style": "typical outfit description",
        "colors": ["primary color", "secondary color"]
    }},
    "backstory": "Character's history and origin (2-3 paragraphs)",
    "motivations": ["motivation1", "motivation2"],
    "quirks": ["quirk1", "quirk2"],
    "voice_description": "How the character sounds",
    "catchphrase": "Optional signature phrase",
    "static_features": "Summary for image generation prompt",
    "dynamic_features": "Changeable aspects"
}}"""
        
        response = await self._call_llm(system_prompt, user_prompt)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()
        
        return json.loads(response)


class MediaGenerator:
    """Generates images and audio using PiAPI"""
    
    def __init__(self, config: GeneratorConfig):
        self.config = config
    
    async def _create_piapi_task(
        self,
        session: aiohttp.ClientSession,
        model: str,
        task_type: str,
        input_data: Dict[str, Any]
    ) -> Optional[str]:
        """Create a PiAPI task"""
        async with session.post(
            "https://api.piapi.ai/api/v1/task",
            headers={
                "X-API-Key": self.config.piapi_api_key,
                "Content-Type": "application/json"
            },
            json={"model": model, "task_type": task_type, "input": input_data}
        ) as resp:
            data = await resp.json()
            if data.get("code") == 200:
                return data["data"]["task_id"]
            return None
    
    async def _poll_piapi_task(
        self,
        session: aiohttp.ClientSession,
        task_id: str,
        timeout: int = 300
    ) -> Optional[Dict[str, Any]]:
        """Poll a PiAPI task until completion"""
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            async with session.get(
                f"https://api.piapi.ai/api/v1/task/{task_id}",
                headers={"X-API-Key": self.config.piapi_api_key}
            ) as resp:
                data = await resp.json()
                status = data["data"]["status"]
                if status == "completed":
                    return data["data"]["output"]
                elif status == "failed":
                    return None
        return None
    
    async def generate_character_portrait(
        self,
        description: str,
        style: str = "3D animated cartoon style"
    ) -> Optional[str]:
        """Generate a character portrait image"""
        prompt = f"""Generate a full-body, front-view portrait of a character with these features:
{description}

Style: {style}
Background: Pure white background
The character should be centered, occupying most of the frame.
High quality, detailed, professional character design."""
        
        async with aiohttp.ClientSession() as session:
            task_id = await self._create_piapi_task(
                session,
                model="Qubico/flux1-dev",
                task_type="txt2img",
                input_data={"prompt": prompt, "width": 1024, "height": 1024}
            )
            if not task_id:
                return None
            
            output = await self._poll_piapi_task(session, task_id)
            if output:
                return output.get("image_url")
        return None
    
    async def generate_side_portrait(
        self,
        front_image_url: str,
        character_name: str
    ) -> Optional[str]:
        """Generate a side view from front portrait"""
        async with aiohttp.ClientSession() as session:
            task_id = await self._create_piapi_task(
                session,
                model="Qubico/flux1-dev",
                task_type="img2img",
                input_data={
                    "prompt": f"Generate a full-body, side-view portrait of this character ({character_name}) with a pure white background. Facing left. Arms relaxed.",
                    "image": front_image_url,
                    "strength": 0.75
                }
            )
            if not task_id:
                return None
            
            output = await self._poll_piapi_task(session, task_id)
            if output:
                return output.get("image_url")
        return None
    
    async def generate_back_portrait(
        self,
        front_image_url: str,
        character_name: str
    ) -> Optional[str]:
        """Generate a back view from front portrait"""
        async with aiohttp.ClientSession() as session:
            task_id = await self._create_piapi_task(
                session,
                model="Qubico/flux1-dev",
                task_type="img2img",
                input_data={
                    "prompt": f"Generate a full-body, back-view portrait of this character ({character_name}) with a pure white background. Facing away. No face visible.",
                    "image": front_image_url,
                    "strength": 0.75
                }
            )
            if not task_id:
                return None
            
            output = await self._poll_piapi_task(session, task_id)
            if output:
                return output.get("image_url")
        return None
    
    async def generate_voice_sample(
        self,
        text: str,
        reference_audio_url: Optional[str] = None
    ) -> Optional[str]:
        """Generate a voice sample using TTS"""
        async with aiohttp.ClientSession() as session:
            input_data = {"gen_text": text}
            
            # Use reference audio if provided, otherwise use a default
            if reference_audio_url:
                input_data["ref_audio"] = reference_audio_url
            else:
                # Use a default reference voice from our S3
                input_data["ref_audio"] = "https://intelli-verse-x-media.s3.amazonaws.com/agent-assets/brands/intelli-verse-x/Characters/C4/voice.mp3"
            
            task_id = await self._create_piapi_task(
                session,
                model="Qubico/tts",
                task_type="zero-shot",
                input_data=input_data
            )
            if not task_id:
                return None
            
            output = await self._poll_piapi_task(session, task_id, timeout=120)
            if output:
                return output.get("audio_url")
        return None
    
    async def generate_logo(
        self,
        brand_name: str,
        description: str,
        style: str = "modern minimalist"
    ) -> Optional[str]:
        """Generate a brand/game logo"""
        prompt = f"""Create a professional logo for "{brand_name}".
Description: {description}
Style: {style}
The logo should be clean, memorable, and work well at any size.
Centered on a transparent or solid color background."""
        
        async with aiohttp.ClientSession() as session:
            task_id = await self._create_piapi_task(
                session,
                model="Qubico/flux1-dev",
                task_type="txt2img",
                input_data={"prompt": prompt, "width": 1024, "height": 1024}
            )
            if not task_id:
                return None
            
            output = await self._poll_piapi_task(session, task_id)
            if output:
                return output.get("image_url")
        return None


class S3Storage:
    """Handle S3 storage operations
    
    S3 Structure Pattern:
        s3://{bucket}/{prefix}/brands/{brand_id}/
            brand.json
            Characters/
                {CharacterName}/
                    character.json
                    front.png (or character.png)
                    side.png
                    back.png
                    voice.m4a
                characters_mapping.json (optional - alias mappings)
        
        s3://{bucket}/{prefix}/games/{game_id}/
            game.json
            Characters/...
    """
    
    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.bucket = config.s3_bucket
        self.prefix = config.s3_prefix.rstrip("/")
        self.region = config.s3_region

    def _get_s3_client(self):
        """boto3 S3 client. Uses AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL from env."""
        kw: Dict[str, Any] = {"region_name": self.region}
        url = os.getenv("AWS_ENDPOINT_URL", "").strip()
        if url:
            kw["endpoint_url"] = url
        return boto3.client("s3", **kw)
    
    def list_objects(self, prefix: str = "", max_keys: int = 100) -> List[Dict[str, Any]]:
        """List objects under prefix (relative to S3_ASSET_PREFIX). Returns [{key, size, last_modified}]."""
        base = self.prefix + "/"
        full_prefix = (base + prefix.strip("/")) if prefix.strip() else base
        try:
            client = self._get_s3_client()
            resp = client.list_objects_v2(Bucket=self.bucket, Prefix=full_prefix, MaxKeys=max(1, min(max_keys, 1000)))
            out = []
            for o in resp.get("Contents") or []:
                out.append({"key": o["Key"], "size": o.get("Size", 0), "last_modified": str(o.get("LastModified", ""))})
            return out
        except Exception:
            return []

    def generate_presigned_url(self, key: str, expires: int = 3600) -> Optional[str]:
        """Generate a presigned GET URL for an S3 object. Key is the full S3 object key (e.g. prefix/path/file)."""
        try:
            client = self._get_s3_client()
            return client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
            )
        except Exception:
            return None
    
    def _get_public_url(self, s3_key: str, filename: str) -> str:
        """Get public URL for an S3 object"""
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{self.prefix}/{s3_key}/{filename}"
    
    def _run_aws_command(self, *args) -> Tuple[bool, str]:
        """Run an AWS CLI command"""
        result = subprocess.run(
            ["aws", "s3", *args],
            capture_output=True,
            text=True
        )
        return result.returncode == 0, result.stdout + result.stderr
    
    async def download_and_upload(
        self,
        source_url: str,
        s3_key: str,
        filename: str,
        public: bool = True
    ) -> Optional[str]:
        """Download from URL and upload to S3"""
        with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as f:
            temp_path = f.name
        
        try:
            # Download
            result = subprocess.run(
                ["curl", "-s", source_url, "-o", temp_path],
                capture_output=True
            )
            if result.returncode != 0:
                return None
            
            # Upload
            s3_path = f"s3://{self.bucket}/{self.prefix}/{s3_key}/{filename}"
            cmd = ["aws", "s3", "cp", temp_path, s3_path]
            if public:
                cmd.extend(["--acl", "public-read"])
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                return None
            
            return self._get_public_url(s3_key, filename)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    async def save_json(
        self, 
        s3_key: str, 
        filename: str, 
        data: Dict[str, Any],
        public: bool = True
    ) -> Optional[str]:
        """Save JSON data to S3"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f, indent=2)
            temp_path = f.name
        
        try:
            s3_path = f"s3://{self.bucket}/{self.prefix}/{s3_key}/{filename}"
            cmd = ["aws", "s3", "cp", temp_path, s3_path]
            if public:
                cmd.extend(["--acl", "public-read"])
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                return None
            
            return self._get_public_url(s3_key, filename)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    async def load_json(self, s3_key: str, filename: str) -> Optional[Dict[str, Any]]:
        """Load JSON data from S3"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name
        
        try:
            s3_path = f"s3://{self.bucket}/{self.prefix}/{s3_key}/{filename}"
            result = subprocess.run(
                ["aws", "s3", "cp", s3_path, temp_path],
                capture_output=True
            )
            if result.returncode != 0:
                return None
            
            with open(temp_path, "r") as f:
                return json.load(f)
        except Exception:
            return None
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def list_items(self, s3_key: str) -> List[str]:
        """List items (folders) in an S3 prefix"""
        s3_path = f"s3://{self.bucket}/{self.prefix}/{s3_key}/"
        result = subprocess.run(
            ["aws", "s3", "ls", s3_path],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return []
        
        items = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.strip().split()
                if parts:
                    # Only get folder names (PRE entries)
                    if "PRE" in line:
                        name = parts[-1].rstrip("/")
                        items.append(name)
                    elif len(parts) >= 4:
                        # File entries have date/time/size/name
                        name = parts[-1].rstrip("/")
                        if not name.endswith(".json"):  # Skip json files
                            items.append(name)
        return items
    
    async def update_characters_mapping(
        self, 
        asset_type: str, 
        asset_id: str,
        char_id: str,
        char_name: str,
        aliases: Optional[List[str]] = None
    ):
        """Update the characters_mapping.json with a new character entry"""
        mapping_key = f"{asset_type}/{asset_id}/Characters"
        mapping = await self.load_json(mapping_key, "characters_mapping.json") or {
            "description": "Maps character IDs and aliases to canonical names",
            "mapping": {},
            "characters": {}
        }
        
        # Add mapping entry
        mapping["mapping"][char_id] = char_name
        if aliases:
            for alias in aliases:
                mapping["mapping"][alias] = char_name
        
        # Add character entry
        mapping["characters"][char_name] = {
            "id": char_id,
            "name": char_name,
            "folder": f"Characters/{char_name}/"
        }
        
        await self.save_json(mapping_key, "characters_mapping.json", mapping)
    
    async def update_asset_characters_list(
        self,
        asset_type: str,
        asset_id: str,
        char_name: str
    ):
        """Add a character to the brand/game's character list"""
        filename = "brand.json" if asset_type == "brands" else "game.json"
        data = await self.load_json(f"{asset_type}/{asset_id}", filename)
        if data:
            if "characters" not in data:
                data["characters"] = []
            if char_name not in data["characters"]:
                data["characters"].append(char_name)
            await self.save_json(f"{asset_type}/{asset_id}", filename, data)
