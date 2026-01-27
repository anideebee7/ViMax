import json
import os
import re
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4


def generate_run_id(prefix: str = "run") -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    token = uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{token}"


def extract_run_id_from_path(working_dir: str) -> Optional[str]:
    """
    Extract run_id from a working directory path.
    
    Looks for:
    1. run.json file in the directory (reads run_id from it)
    2. Directory name matching run_id pattern (prefix_timestamp_token)
    
    Args:
        working_dir: Path to working directory
        
    Returns:
        run_id if found, None otherwise
    """
    if not working_dir or not os.path.exists(working_dir):
        return None
    
    # Try to read from run.json
    run_json_path = os.path.join(working_dir, "run.json")
    if os.path.exists(run_json_path):
        try:
            with open(run_json_path, "r") as f:
                data = json.load(f)
                return data.get("run_id")
        except Exception:
            pass
    
    # Try to extract from directory name (pattern: prefix_YYYYMMDD_HHMMSS_token)
    dir_name = os.path.basename(os.path.abspath(working_dir))
    # Pattern: prefix_YYYYMMDD_HHMMSS_8hexchars
    pattern = r'^(\w+)_(\d{8}_\d{6})_([a-f0-9]{8})$'
    match = re.match(pattern, dir_name)
    if match:
        return dir_name  # Return the full directory name as run_id
    
    return None


def write_run_metadata(
    run_dir: str,
    pipeline_name: str,
    run_id: str,
    extra: Optional[Dict[str, str]] = None,
) -> None:
    os.makedirs(run_dir, exist_ok=True)
    payload = {
        "run_id": run_id,
        "pipeline": pipeline_name,
        "started_at_utc": datetime.utcnow().isoformat() + "Z",
    }
    if extra:
        payload.update(extra)
    path = os.path.join(run_dir, "run.json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def initialize_run_directory(
    working_dir: str,
    pipeline_name: str,
    run_id: Optional[str] = None,
    use_run_id: bool = True,
) -> tuple[str, Optional[str]]:
    """
    Initialize run directory with proper resume detection.
    
    This function handles:
    1. Extracting run_id from existing working_dir if not provided
    2. Detecting resume scenarios (existing run_id directory)
    3. Creating new run_id only when necessary
    4. Ensuring working_dir points to the correct location
    
    Args:
        working_dir: Base working directory path
        pipeline_name: Name of the pipeline (for run_id prefix)
        run_id: Optional run_id to use (if None, will try to extract or generate)
        use_run_id: Whether to use run_id subdirectories
        
    Returns:
        Tuple of (final_working_dir, run_id)
    """
    base_working_dir = working_dir
    
    # If run_id not provided but working_dir exists, try to extract run_id from it
    if not run_id and use_run_id:
        extracted_run_id = extract_run_id_from_path(working_dir)
        if extracted_run_id:
            run_id = extracted_run_id
    
    # If working_dir is provided and is an absolute path to an existing run directory,
    # and run_id matches the directory name, use it directly (resume scenario)
    abs_working_dir = os.path.abspath(working_dir)
    dir_name = os.path.basename(abs_working_dir)
    if run_id and dir_name == run_id and os.path.exists(abs_working_dir):
        # Resume scenario: working_dir is already the run_id directory
        final_working_dir = abs_working_dir
        final_run_id = run_id
    else:
        # Normal initialization path: create run_id subdirectory
        final_run_id = run_id or (generate_run_id(pipeline_name) if use_run_id else None)
        final_working_dir = (
            os.path.join(base_working_dir, final_run_id)
            if use_run_id and final_run_id
            else base_working_dir
        )
    
    # Ensure directory exists
    os.makedirs(final_working_dir, exist_ok=True)
    
    # Write metadata only if it doesn't exist (resume scenario)
    if use_run_id and final_run_id:
        run_json_path = os.path.join(final_working_dir, "run.json")
        if not os.path.exists(run_json_path):
            write_run_metadata(final_working_dir, pipeline_name, final_run_id)
    
    return final_working_dir, final_run_id
