"""
S3 Character Loader Utility

Loads characters from S3 and converts them to ViMax's expected format
for use in video/content generation pipelines.

S3 Structure Expected:
    s3://{bucket}/{prefix}/brands/{brand_id}/
        brand.json                    # Optional: lists characters
        Characters/
            {character_name}/
                character.json        # Character metadata
                front.png             # Or character.png, character.jpg
                side.png
                back.png
                voice.m4a             # Optional voice sample
            characters_mapping.json   # Optional: alias mappings
"""
import os
import json
import subprocess
import tempfile
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from utils.media.image import download_image as _http_download_image
from interfaces import CharacterInScene


logger = logging.getLogger(__name__)


@dataclass
class S3Config:
    """Configuration for S3 access"""
    bucket: str = "intelli-verse-x-media"
    prefix: str = "agent-assets"
    region: str = "us-east-1"
    
    @property
    def base_url(self) -> str:
        """Get base URL for public access"""
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{self.prefix}"
    
    @property
    def s3_uri(self) -> str:
        """Get S3 URI for CLI commands"""
        return f"s3://{self.bucket}/{self.prefix}"
    
    @classmethod
    def from_env(cls) -> "S3Config":
        return cls(
            bucket=os.getenv("AWS_S3_BUCKET_NAME", "intelli-verse-x-media"),
            prefix=os.getenv("S3_ASSET_PREFIX", "agent-assets"),
            region=os.getenv("AWS_REGION", "us-east-1"),
        )


@dataclass
class CharacterData:
    """Standardized character data structure"""
    id: str
    name: str
    identifier_in_scene: str
    is_visible: bool = True
    role: str = "character"
    description: str = ""
    appearance: str = ""
    static_features: str = ""
    dynamic_features: str = "None"
    public_urls: Dict[str, str] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    raw_data: Dict = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict, base_url: str = "") -> "CharacterData":
        """Create CharacterData from a dictionary (character.json content)
        
        Supports both legacy format (front/side/back views) and new format
        with character sheets and expression variants.
        """
        char_id = data.get("id", data.get("name", "unknown"))
        name = data.get("name", char_id)
        identifier = data.get("identifier_in_scene", name)
        
        # Build public URLs - support multiple formats including new character sheet
        public_urls = {}
        urls_data = data.get("public_urls", {})
        
        # Character sheet (new format)
        sheet_url = urls_data.get("character_sheet") or urls_data.get("sheet")
        if sheet_url:
            public_urls["character_sheet"] = sheet_url
            public_urls["sheet"] = sheet_url
        
        # Views with expression variants (new format)
        expressions = ["neutral", "happy", "sad"]
        for view in ["front", "side", "back"]:
            # Check for expression variants
            for expr in expressions:
                expr_key = f"{view}_{expr}"
                url = urls_data.get(expr_key)
                if url:
                    public_urls[expr_key] = url
            
            # Legacy format (view only)
            url = (
                urls_data.get(view) or 
                urls_data.get(f"portrait_{view}") or
                urls_data.get(f"{view}_url") or
                ""
            )
            if url:
                public_urls[view] = url
                public_urls[f"portrait_{view}"] = url
        
        # Voice URL
        voice_url = urls_data.get("voice", "")
        if voice_url:
            public_urls["voice"] = voice_url
        
        return cls(
            id=char_id,
            name=name,
            identifier_in_scene=identifier,
            is_visible=data.get("is_visible", True),
            role=data.get("role", "character"),
            description=data.get("description", ""),
            appearance=data.get("appearance", ""),
            static_features=data.get("static_features", ""),
            dynamic_features=data.get("dynamic_features", "None"),
            public_urls=public_urls,
            aliases=data.get("aliases", []),
            raw_data=data,
        )
    
    def to_vimax_character(self, idx: int = 0) -> CharacterInScene:
        """Convert to ViMax CharacterInScene format with full profile data"""
        return CharacterInScene(
            idx=idx,
            identifier_in_scene=self.identifier_in_scene,
            is_visible=self.is_visible,
            static_features=self.static_features,
            dynamic_features=self.dynamic_features,
            # Rich character profile data
            description=self.description,
            personality=self.raw_data.get("personality"),
            voice_description=self.raw_data.get("voice"),
            role=self.role,
            traits=self.raw_data.get("traits"),
            appearance=self.appearance,
        )


class S3CharacterLoader:
    """Load characters from S3 and convert to ViMax format
    
    Generic loader that works with any brand/game structure.
    Automatically discovers characters from S3 if brand.json doesn't exist.
    """
    
    def __init__(self, config: Optional[S3Config] = None):
        self.config = config or S3Config.from_env()
        self._alias_cache: Dict[str, str] = {}  # alias -> canonical name
        self._character_cache: Dict[str, CharacterData] = {}  # id -> CharacterData
    
    def _run_s3_command(self, *args) -> Tuple[bool, str, str]:
        """Run an AWS S3 CLI command"""
        result = subprocess.run(
            ["aws", "s3", *args],
            capture_output=True,
            text=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    
    def _s3_exists(self, s3_path: str) -> bool:
        """Check if S3 path exists"""
        success, stdout, _ = self._run_s3_command("ls", s3_path)
        return success and len(stdout.strip()) > 0
    
    def _download_json(self, s3_path: str) -> Optional[Dict]:
        """Download and parse JSON from S3"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name
        
        try:
            result = subprocess.run(
                ["aws", "s3", "cp", s3_path, temp_path],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                return None
            
            with open(temp_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error downloading {s3_path}: {e}")
            return None
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def _upload_json(self, data: Dict, s3_path: str, public: bool = True) -> bool:
        """Upload JSON to S3"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
            json.dump(data, f, indent=2)
            temp_path = f.name
        
        try:
            args = ["aws", "s3", "cp", temp_path, s3_path]
            if public:
                args.extend(["--acl", "public-read"])
            result = subprocess.run(args, capture_output=True, text=True)
            return result.returncode == 0
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def _list_s3_folders(self, s3_path: str) -> List[str]:
        """List folder names at S3 path"""
        success, output, _ = self._run_s3_command("ls", s3_path)
        if not success:
            return []
        
        folders = []
        for line in output.strip().split('\n'):
            if line.strip() and 'PRE' in line:
                folder = line.split()[-1].rstrip('/')
                folders.append(folder)
        return folders
    
    def load_brand_ecosystem(self, brand_id: str) -> Dict[str, Any]:
        """Load the full brand ecosystem configuration from S3.
        
        Expects a structure where brand.json lists flavors, and each flavor 
        has its own flavor.json with keywords, pillars, and channel info.
        """
        brand_data = self.load_brand_json(brand_id) or {}
        flavors_list = brand_data.get("flavors", [])
        
        ecosystem = {
            "brand": brand_data,
            "flavors": {}
        }
        
        for flavor in flavors_list:
            flavor_data = self._download_json(
                f"{self.config.s3_uri}/brands/{brand_id}/flavors/{flavor}/flavor.json"
            )
            if flavor_data:
                ecosystem["flavors"][flavor] = flavor_data
                
        return ecosystem

    def list_brands(self) -> List[str]:
        """List all available brands"""
        return self._list_s3_folders(f"{self.config.s3_uri}/brands/")
    
    def list_games(self) -> List[str]:
        """List all available games"""
        return self._list_s3_folders(f"{self.config.s3_uri}/games/")
    
    def list_characters(self, asset_type: str, asset_id: str) -> List[str]:
        """List all character folders for a brand/game
        
        Args:
            asset_type: 'brands' or 'games'
            asset_id: brand or game ID
        
        Returns:
            List of character folder names
        """
        s3_path = f"{self.config.s3_uri}/{asset_type}/{asset_id}/Characters/"
        return self._list_s3_folders(s3_path)
    
    def load_brand_json(self, brand_id: str) -> Optional[Dict]:
        """Load brand.json from S3"""
        return self._download_json(
            f"{self.config.s3_uri}/brands/{brand_id}/brand.json"
        )
    
    def load_game_json(self, game_id: str) -> Optional[Dict]:
        """Load game.json from S3"""
        return self._download_json(
            f"{self.config.s3_uri}/games/{game_id}/game.json"
        )
    
    def load_character_mapping(self, asset_type: str, asset_id: str) -> Dict[str, str]:
        """Load character alias mapping if available
        
        Returns:
            Dict mapping aliases to canonical character names
        """
        mapping_path = f"{self.config.s3_uri}/{asset_type}/{asset_id}/Characters/characters_mapping.json"
        data = self._download_json(mapping_path)
        if data and "mapping" in data:
            return data["mapping"]
        return {}
    
    def load_character_json(
        self, 
        asset_type: str, 
        asset_id: str, 
        char_id: str
    ) -> Optional[Dict]:
        """Load character.json from S3
        
        Args:
            asset_type: 'brands' or 'games'
            asset_id: brand or game ID
            char_id: character ID/name (folder name)
        """
        return self._download_json(
            f"{self.config.s3_uri}/{asset_type}/{asset_id}/Characters/{char_id}/character.json"
        )
    
    def _discover_character_assets(
        self, 
        asset_type: str, 
        asset_id: str, 
        char_id: str
    ) -> Dict[str, str]:
        """Discover available portrait assets for a character
        
        Returns dict of discovered public URLs
        """
        base_s3 = f"{self.config.s3_uri}/{asset_type}/{asset_id}/Characters/{char_id}"
        base_url = f"{self.config.base_url}/{asset_type}/{asset_id}/Characters/{char_id}"
        
        urls = {}
        
        # Check for front portrait (multiple naming conventions)
        for name in [
            "front.png",
            "Front.png",
            "character.png",
            "Character.png",
            "character.jpg",
            "Character.jpg",
            "front.jpg",
            "Front.jpg",
        ]:
            if self._s3_exists(f"{base_s3}/{name}"):
                urls["front"] = f"{base_url}/{name}"
                urls["portrait_front"] = f"{base_url}/{name}"
                break

        # Check for side portrait
        for name in ["side.png", "Side.png", "side.jpg", "Side.jpg"]:
            if self._s3_exists(f"{base_s3}/{name}"):
                urls["side"] = f"{base_url}/{name}"
                urls["portrait_side"] = f"{base_url}/{name}"
                break

        # Check for back portrait
        for name in ["back.png", "Back.png", "back.jpg", "Back.jpg"]:
            if self._s3_exists(f"{base_s3}/{name}"):
                urls["back"] = f"{base_url}/{name}"
                urls["portrait_back"] = f"{base_url}/{name}"
                break
        
        # Check for voice
        for ext in ["m4a", "mp3", "wav"]:
            if self._s3_exists(f"{base_s3}/voice.{ext}"):
                urls["voice"] = f"{base_url}/voice.{ext}"
                break
        
        return urls
    
    def load_character(
        self, 
        asset_type: str, 
        asset_id: str, 
        char_id: str,
        discover_assets: bool = True
    ) -> Optional[CharacterData]:
        """Load a single character with full data
        
        Args:
            asset_type: 'brands' or 'games'
            asset_id: brand or game ID  
            char_id: character ID/folder name
            discover_assets: If True, discovers assets from S3 if not in character.json
        
        Returns:
            CharacterData object or None if not found
        """
        # Check cache
        cache_key = f"{asset_type}/{asset_id}/{char_id}"
        if cache_key in self._character_cache:
            return self._character_cache[cache_key]
        
        # Load character.json
        char_data = self.load_character_json(asset_type, asset_id, char_id)
        
        if char_data is None:
            # No character.json - try to build from discovered assets
            if discover_assets:
                discovered_urls = self._discover_character_assets(asset_type, asset_id, char_id)
                if discovered_urls:
                    char_data = {
                        "id": char_id,
                        "name": char_id,
                        "identifier_in_scene": char_id,
                        "public_urls": discovered_urls,
                    }
                    logger.info(f"Discovered character {char_id} from assets (no character.json)")
                else:
                    return None
            else:
                return None
        
        # Ensure public_urls are complete by discovering any missing assets
        if discover_assets:
            discovered = self._discover_character_assets(asset_type, asset_id, char_id)
            existing_urls = char_data.get("public_urls", {})
            # Merge discovered URLs (don't overwrite existing)
            for key, url in discovered.items():
                if key not in existing_urls or not existing_urls[key]:
                    existing_urls[key] = url
            char_data["public_urls"] = existing_urls
        
        # Create CharacterData
        character = CharacterData.from_dict(char_data, self.config.base_url)
        
        # Cache it
        self._character_cache[cache_key] = character
        
        # Also cache aliases
        for alias in character.aliases:
            self._alias_cache[alias] = char_id
        
        return character
    
    def load_brand_characters(
        self, 
        brand_id: str,
        selected_identifiers: Optional[List[str]] = None
    ) -> List[CharacterData]:
        """Load all characters for a brand
        
        Args:
            brand_id: Brand identifier
            selected_identifiers: Optional list of character IDs to load (supports aliases)
        
        Returns:
            List of CharacterData objects
        """
        # Load alias mapping first
        alias_mapping = self.load_character_mapping("brands", brand_id)
        self._alias_cache.update(alias_mapping)
        
        # Get character list from brand.json or discover from S3
        brand_data = self.load_brand_json(brand_id)
        
        if brand_data and "characters" in brand_data:
            char_ids = brand_data["characters"]
        else:
            # Discover characters by listing S3 folders
            char_ids = self.list_characters("brands", brand_id)
            logger.info(f"Discovered {len(char_ids)} characters from S3: {char_ids}")
        
        # Filter by selected identifiers (resolve aliases) - CASE INSENSITIVE
        if selected_identifiers:
            resolved_lower = set()
            for identifier in selected_identifiers:
                # Check if it's an alias
                canonical = self._alias_cache.get(identifier, identifier)
                resolved_lower.add(canonical.lower())
            # Case-insensitive matching
            char_ids = [c for c in char_ids if c.lower() in resolved_lower]
        
        # Load each character (try case-insensitive if exact match fails)
        characters = []
        # Get actual S3 folder names for case-insensitive fallback
        s3_folders = self.list_characters("brands", brand_id)
        s3_folder_map = {f.lower(): f for f in s3_folders}
        
        for char_id in char_ids:
            char = self.load_character("brands", brand_id, char_id)
            if not char:
                # Try case-insensitive S3 folder lookup
                actual_folder = s3_folder_map.get(char_id.lower())
                if actual_folder and actual_folder != char_id:
                    char = self.load_character("brands", brand_id, actual_folder)
            if char:
                characters.append(char)
        
        return characters
    
    def load_game_characters(
        self, 
        game_id: str,
        selected_identifiers: Optional[List[str]] = None
    ) -> List[CharacterData]:
        """Load all characters for a game"""
        # Load alias mapping first
        alias_mapping = self.load_character_mapping("games", game_id)
        self._alias_cache.update(alias_mapping)
        
        # Get character list
        game_data = self.load_game_json(game_id)
        
        if game_data and "characters" in game_data:
            char_ids = game_data["characters"]
        else:
            char_ids = self.list_characters("games", game_id)
        
        # Filter by selected identifiers - CASE INSENSITIVE
        if selected_identifiers:
            resolved_lower = set()
            for identifier in selected_identifiers:
                canonical = self._alias_cache.get(identifier, identifier)
                resolved_lower.add(canonical.lower())
            # Case-insensitive matching
            char_ids = [c for c in char_ids if c.lower() in resolved_lower]
        
        # Load each character (try case-insensitive if exact match fails)
        characters = []
        # Get actual S3 folder names for case-insensitive fallback
        s3_folders = self.list_characters("games", game_id)
        s3_folder_map = {f.lower(): f for f in s3_folders}
        
        for char_id in char_ids:
            char = self.load_character("games", game_id, char_id)
            if not char:
                # Try case-insensitive S3 folder lookup
                actual_folder = s3_folder_map.get(char_id.lower())
                if actual_folder and actual_folder != char_id:
                    char = self.load_character("games", game_id, actual_folder)
            if char:
                characters.append(char)
        
        return characters
    
    def resolve_character_alias(self, identifier: str) -> str:
        """Resolve a character alias to its canonical name"""
        return self._alias_cache.get(identifier, identifier)
    
    def to_vimax_characters(
        self,
        characters: List[CharacterData],
        selected_identifiers: Optional[List[str]] = None
    ) -> List[CharacterInScene]:
        """Convert CharacterData list to ViMax CharacterInScene format"""
        vimax_chars = []
        
        # Normalize selected identifiers for case-insensitive matching
        selected_lower = None
        if selected_identifiers:
            selected_lower = {s.lower() for s in selected_identifiers}
        
        for idx, char in enumerate(characters):
            if selected_lower:
                # Case-insensitive check if character or any alias matches
                matches = (
                    char.identifier_in_scene.lower() in selected_lower or
                    char.id.lower() in selected_lower or
                    any(alias.lower() in selected_lower for alias in char.aliases)
                )
                if not matches:
                    continue
            
            vimax_chars.append(char.to_vimax_character(idx))
        
        return vimax_chars
    
    def to_vimax_portrait_registry(
        self,
        characters: List[CharacterData],
        download_dir: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Convert characters to ViMax portrait registry format
        
        Supports both legacy format (front/side/back views only) and new format
        with character sheets and expression variants.
        
        Args:
            characters: List of CharacterData
            download_dir: Optional directory to download portraits to
        
        Returns:
            Dict mapping identifier -> {
                sheet: {path, description},  # NEW: Full character sheet
                front: {
                    neutral: {path, description},  # NEW: Expression variants
                    happy: {path, description},
                    sad: {path, description},
                    path: str,  # LEGACY: Backwards compatible
                    description: str,
                },
                side: {...},
                back: {...},
            }
        """
        registry = {}
        # Sanitize identifier for use in paths (remove / and other problematic chars)
        def _safe_dir(name: str) -> str:
            return "".join(c for c in name if c.isalnum() or c in "._- ") or "character"
        
        expressions = ["neutral", "happy", "sad"]
        
        for char in characters:
            identifier = char.identifier_in_scene
            safe_id = _safe_dir(identifier) or "character"
            char_portraits = {}
            
            # Check for character sheet (new format)
            sheet_url = char.public_urls.get("character_sheet") or char.public_urls.get("sheet")
            if sheet_url:
                path = sheet_url
                if download_dir:
                    local_path = os.path.join(download_dir, safe_id, "character_sheet.png")
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    try:
                        _http_download_image(sheet_url, local_path)
                        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                            path = local_path
                    except Exception as e:
                        logger.warning(f"Character sheet download failed for {identifier}: {e}")
                
                char_portraits["sheet"] = {
                    "path": path,
                    "description": f"Full character sheet for {char.name}"
                }
            
            # Load views (front/side/back)
            for view in ["front", "side", "back"]:
                view_data = {}
                
                # Check for expression variants (new format)
                has_expressions = False
                for expr in expressions:
                    expr_key = f"{view}_{expr}"
                    url = char.public_urls.get(expr_key)
                    if url:
                        has_expressions = True
                        path = url
                        if download_dir:
                            ext = (url.split("?")[0].split(".")[-1] or "png").lower()
                            if ext not in ("png", "jpg", "jpeg", "webp"):
                                ext = "png"
                            local_path = os.path.join(download_dir, safe_id, f"{view}_{expr}.{ext}")
                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                            try:
                                _http_download_image(url, local_path)
                                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                                    path = local_path
                            except Exception as e:
                                logger.warning(f"Portrait download failed for {identifier} {view}_{expr}: {e}")
                        
                        view_data[expr] = {
                            "path": path,
                            "description": f"{view.capitalize()} view, {expr} expression of {char.name}"
                        }
                
                # Fall back to legacy format (view only, no expression)
                if not has_expressions:
                    url = char.public_urls.get(view) or char.public_urls.get(f"portrait_{view}")
                    if url:
                        path = url
                        if download_dir:
                            ext = (url.split("?")[0].split(".")[-1] or "png").lower()
                            if ext not in ("png", "jpg", "jpeg", "webp"):
                                ext = "png"
                            local_path = os.path.join(download_dir, safe_id, f"{view}.{ext}")
                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                            try:
                                _http_download_image(url, local_path)
                                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                                    path = local_path
                                else:
                                    logger.warning(f"Portrait download empty or missing: {local_path}")
                            except Exception as e:
                                logger.warning(f"Portrait download failed for {identifier} {view}: {e}, using URL")
                        
                        # Legacy format with path/description at view level
                        view_data["path"] = path
                        view_data["description"] = f"{view.capitalize()} view of {char.name}"
                        # Also set neutral for compatibility with new format
                        view_data["neutral"] = {
                            "path": path,
                            "description": f"{view.capitalize()} view, neutral expression of {char.name}"
                        }
                
                if view_data:
                    char_portraits[view] = view_data
            
            if char_portraits:
                registry[identifier] = char_portraits
        
        return registry
    
    def get_character_portrait_overrides(
        self,
        characters: List[CharacterData],
        download_dir: str
    ) -> Dict[str, Dict[str, str]]:
        """Get character portrait overrides for ViMax config
        
        Downloads portraits to local directory and returns override dict
        suitable for video.yaml character_portrait_overrides
        """
        overrides = {}
        
        for char in characters:
            identifier = char.identifier_in_scene
            char_dir = os.path.join(download_dir, identifier)
            os.makedirs(char_dir, exist_ok=True)
            
            override = {}
            
            for view in ["front", "side", "back"]:
                url = char.public_urls.get(view) or char.public_urls.get(f"portrait_{view}")
                if not url:
                    continue
                
                ext = url.split(".")[-1]
                local_path = os.path.join(char_dir, f"{view}.{ext}")
                
                result = subprocess.run(
                    ["curl", "-s", url, "-o", local_path],
                    capture_output=True
                )
                
                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    override[f"{view}_path"] = local_path
            
            if override:
                overrides[identifier] = override
        
        return overrides


# Convenience functions for quick access

def load_brand_characters_for_vimax(
    brand_id: str,
    selected_identifiers: Optional[List[str]] = None,
    config: Optional[S3Config] = None
) -> Tuple[List[CharacterInScene], Dict]:
    """Load brand characters in ViMax-ready format
    
    Args:
        brand_id: Brand identifier
        selected_identifiers: Optional list of character IDs to include
        config: Optional S3Config override
    
    Returns:
        Tuple of (list of CharacterInScene, portrait registry dict)
    """
    loader = S3CharacterLoader(config)
    characters = loader.load_brand_characters(brand_id, selected_identifiers)
    
    vimax_chars = loader.to_vimax_characters(characters)
    portrait_registry = loader.to_vimax_portrait_registry(characters)
    
    return vimax_chars, portrait_registry


def load_game_characters_for_vimax(
    game_id: str,
    selected_identifiers: Optional[List[str]] = None,
    config: Optional[S3Config] = None
) -> Tuple[List[CharacterInScene], Dict]:
    """Load game characters in ViMax-ready format"""
    loader = S3CharacterLoader(config)
    characters = loader.load_game_characters(game_id, selected_identifiers)
    
    vimax_chars = loader.to_vimax_characters(characters)
    portrait_registry = loader.to_vimax_portrait_registry(characters)
    
    return vimax_chars, portrait_registry


def download_brand_characters(
    brand_id: str,
    download_dir: str,
    selected_identifiers: Optional[List[str]] = None,
    config: Optional[S3Config] = None
) -> Dict[str, Dict[str, str]]:
    """Download brand character portraits and return overrides for ViMax config
    
    Returns:
        Dict of character_portrait_overrides for video.yaml
    """
    loader = S3CharacterLoader(config)
    characters = loader.load_brand_characters(brand_id, selected_identifiers)
    return loader.get_character_portrait_overrides(characters, download_dir)
