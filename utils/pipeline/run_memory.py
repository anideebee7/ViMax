import os
import json
import subprocess
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RunMemoryConfig:
    bucket: str = "intelli-verse-x-media"
    base_prefix: str = "agent-assets/memory"
    
    @property
    def s3_base_uri(self) -> str:
        return f"s3://{self.bucket}/{self.base_prefix}"

class RunMemory:
    """Utility to sync pipeline run state and assets to S3 for persistent memory."""
    
    def __init__(self, pipeline_type: str, run_id: str, local_dir: str, config: Optional[RunMemoryConfig] = None):
        self.pipeline_type = pipeline_type
        self.run_id = run_id
        self.local_dir = local_dir
        self.config = config or RunMemoryConfig()
        
        # Structure: s3://{bucket}/agent-assets/memory/{pipeline_type}/{run_id}/
        self.s3_run_uri = f"{self.config.s3_base_uri}/{pipeline_type}/{run_id}"
        
    def _run_s3_command(self, *args) -> bool:
        """Run an AWS S3 CLI command"""
        try:
            result = subprocess.run(
                ["aws", "s3", *args],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.error(f"S3 command failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error running S3 command: {e}")
            return False

    def sync_to_s3(self, exclude_patterns: Optional[list] = None) -> bool:
        """Upload local working directory to S3"""
        if not os.path.exists(self.local_dir):
            logger.warning(f"Local directory {self.local_dir} does not exist. Nothing to sync.")
            return False
            
        logger.info(f"☁️ Syncing run {self.run_id} to S3: {self.s3_run_uri}")
        args = ["sync", self.local_dir, self.s3_run_uri, "--acl", "public-read"]
        
        if exclude_patterns:
            for pattern in exclude_patterns:
                args.extend(["--exclude", pattern])
                
        return self._run_s3_command(*args)

    def sync_from_s3(self) -> bool:
        """Download run state from S3 to local working directory"""
        logger.info(f"☁️ Fetching run {self.run_id} memory from S3...")
        os.makedirs(self.local_dir, exist_ok=True)
        return self._run_s3_command("sync", self.s3_run_uri, self.local_dir)

    def put_metadata(self, key: str, data: Dict[str, Any]) -> bool:
        """Upload a specific piece of metadata to S3 memory"""
        temp_path = os.path.join(self.local_dir, f"{key}.json")
        os.makedirs(self.local_dir, exist_ok=True)
        
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        s3_path = f"{self.s3_run_uri}/{key}.json"
        success = self._run_s3_command("cp", temp_path, s3_path, "--acl", "public-read")
        return success

    def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific piece of metadata from S3 memory"""
        s3_path = f"{self.s3_run_uri}/{key}.json"
        temp_path = os.path.join(self.local_dir, f"{key}_remote.json")
        
        success = self._run_s3_command("cp", s3_path, temp_path)
        if not success or not os.path.exists(temp_path):
            return None
            
        try:
            with open(temp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @property
    def memory_uri(self) -> str:
        return self.s3_run_uri
