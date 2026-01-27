import base64
import os
import time
import asyncio
from typing import Any, Dict, Optional

import aiohttp


class PiAPIClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.piapi.ai/api/v1/task",
        upload_url: str = "https://upload.theapi.app/api/ephemeral_resource",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.upload_url = upload_url

    async def create_task(
        self,
        model: str,
        task_type: str,
        input_data: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        retry_delay: int = 5,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "task_type": task_type,
            "input": input_data,
        }
        if config:
            payload["config"] = config

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.base_url, json=payload, headers=headers) as response:
                        response.raise_for_status()
                        return await response.json()
            except aiohttp.ClientResponseError as e:
                last_error = e
                # Retry on 500-level errors (server issues)
                if 500 <= e.status < 600 and attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                raise
        raise last_error

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        headers = {
            "X-API-Key": self.api_key,
        }
        url = f"{self.base_url}/{task_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.json()

    async def wait_for_task(
        self,
        task_id: str,
        timeout_seconds: int = 900,
        poll_interval_seconds: int = 2,
    ) -> Dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while True:
            payload = await self.get_task(task_id)
            data = payload.get("data", {})
            status = (data.get("status") or "").lower()
            if status in {"completed", "succeeded"}:
                return payload
            if status in {"failed", "error"}:
                return payload
            if time.time() > deadline:
                raise TimeoutError(f"PiAPI task {task_id} timed out after {timeout_seconds}s")
            await asyncio.sleep(poll_interval_seconds)

    async def upload_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        file_name = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "file_name": file_name,
            "file_data": file_data,
        }

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.upload_url, json=payload, headers=headers) as response:
                response.raise_for_status()
                response_json = await response.json()
                data = response_json.get("data", {})
                url = data.get("url")
                if not url:
                    raise RuntimeError("PiAPI upload did not return a URL")
                return url
