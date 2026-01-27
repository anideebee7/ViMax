import json
import os
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4


def generate_run_id(prefix: str = "run") -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    token = uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{token}"


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
