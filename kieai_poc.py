import asyncio
import aiohttp
import os
import logging
from dotenv import load_dotenv

load_dotenv()

KIEAI_API_KEY = os.getenv("KIEAI_API_KEY")
BASE_URL = "https://api.kie.ai/api/v1"

async def test_kieai_endpoints():
    headers = {
        "Authorization": f"Bearer {KIEAI_API_KEY}",
        "Content-Type": "application/json",
    }
    
    print("--- 1. Generating a Video (KieAI) ---", flush=True)
    payload = {
        "prompt": "A small cute robot dancing in a field of neon flowers, high quality 3d animation",
        "model": "veo3_fast",
        "aspect_ratio": "16:9",
        "generationType": "TEXT_2_VIDEO"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/veo/generate", headers=headers, json=payload) as response:
            res_json = await response.json()
            print(f"Task Creation Response: {res_json}", flush=True)
            if res_json.get("code") != 200:
                print("Failed to create task.", flush=True)
                return
            task_id = res_json["data"]["taskId"]
            print(f"Created Task ID: {task_id}", flush=True)
            
    # Polling for status using record-info (Proof of Concept)
    print("\n--- 2. Checking Status using /veo/record-info (PoC) ---", flush=True)
    video_url = None
    for _ in range(60): # 5 minutes max
        async with aiohttp.ClientSession() as session:
            # Using the new record-info endpoint as requested
            async with session.get(f"{BASE_URL}/veo/record-info?taskId={task_id}", headers=headers) as response:
                res_json = await response.json()
                data = res_json.get("data", {})
                success_flag = data.get("successFlag")
                
                # successFlag: 0=Generating, 1=Success, 2=Failed, 3=Gen Failed
                if success_flag == 1:
                    print(f"Task Success! Data: {res_json}", flush=True)
                    video_url = data.get("response", {}).get("resultUrls", [None])[0]
                    print(f"Video URL: {video_url}", flush=True)
                    break
                elif success_flag in [2, 3]:
                    print(f"Task Failed! Response: {res_json}", flush=True)
                    return
                else:
                    print(f"Task in progress (flag: {success_flag})... waiting 10s", flush=True)
                    await asyncio.sleep(10)
    
    if not video_url:
        print("Timeout or no video URL found.", flush=True)
        return
        
    print("\n--- 3. Testing /veo/extend (PoC) ---", flush=True)
    # Now we extend the video we just created
    extend_payload = {
        "prompt": "The robot now jumps into the air with joy as the flowers glow brighter",
        "task_id": task_id, # Based on the docs for extend
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/veo/extend", headers=headers, json=extend_payload) as response:
            res_json = await response.json()
            print(f"Extend Response: {res_json}", flush=True)
            if res_json.get("code") == 200:
                extend_task_id = res_json["data"]["taskId"]
                print(f"Extend Task ID: {extend_task_id}", flush=True)
                
                # Poll for extend status as well
                print("\n--- 4. Checking Extend Status ---", flush=True)
                for _ in range(30):
                    async with session.get(f"{BASE_URL}/veo/record-info?taskId={extend_task_id}", headers=headers) as resp:
                        ext_json = await resp.json()
                        ext_flag = ext_json.get("data", {}).get("successFlag")
                        if ext_flag == 1:
                            ext_url = ext_json.get("data", {}).get("response", {}).get("resultUrls", [None])[0]
                            print(f"Extension Success! Extended Video URL: {ext_url}", flush=True)
                            break
                        elif ext_flag in [2, 3]:
                            print(f"Extension Failed! Response: {ext_json}", flush=True)
                            break
                        else:
                            print(f"Extension in progress... waiting 10s", flush=True)
                            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(test_kieai_endpoints())
