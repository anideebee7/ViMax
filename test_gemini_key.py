#!/usr/bin/env python3
"""
Test Gemini API key validity
"""
import os
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

load_dotenv()

async def test_gemini_key(api_key: str):
    """Test if the Gemini API key is valid by making a simple image generation request."""
    print(f"🔑 Testing Gemini API Key...")
    print(f"   Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"   Length: {len(api_key)} characters\n")
    
    try:
        # Initialize client
        client = genai.Client(api_key=api_key)
        print("✅ Client initialized successfully")
        
        # Try a simple image generation request
        print("🖼️  Testing image generation...")
        model = "gemini-2.5-flash-image"
        
        response = await client.aio.models.generate_content(
            model=model,
            contents="A simple test image: a red circle on white background",
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="1:1",
                ),
            ),
        )
        
        # Check if we got an image
        image_found = False
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_found = True
                print(f"✅ Image generated successfully!")
                print(f"   Image size: {len(part.inline_data.data)} bytes")
                break
        
        if not image_found:
            print("⚠️  No image in response, but API call succeeded")
        
        print("\n✅ API KEY IS VALID AND WORKING!")
        return True
        
    except ClientError as e:
        error_code = e.args[0].get('error', {}).get('code', 'UNKNOWN')
        error_message = e.args[0].get('error', {}).get('message', str(e))
        
        if error_code == 400 and 'API key not valid' in error_message:
            print(f"❌ API KEY IS INVALID")
            print(f"   Error: {error_message}")
            return False
        else:
            print(f"⚠️  API call failed with error:")
            print(f"   Code: {error_code}")
            print(f"   Message: {error_message}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing API key: {e}")
        print(f"   Type: {type(e).__name__}")
        return False

async def main():
    # Test the new key
    new_key = "AIzaSyCdELpw0hfxZ5zlzuPzWedasW2f08nFVEc"
    print("=" * 60)
    print("TESTING NEW GEMINI API KEY")
    print("=" * 60)
    result_new = await test_gemini_key(new_key)
    
    print("\n" + "=" * 60)
    print("TESTING CURRENT .env KEY")
    print("=" * 60)
    current_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if current_key:
        result_current = await test_gemini_key(current_key)
    else:
        print("❌ No GEMINI_API_KEY or GOOGLE_API_KEY found in .env")
        result_current = False
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"New Key: {'✅ VALID' if result_new else '❌ INVALID'}")
    print(f"Current Key: {'✅ VALID' if result_current else '❌ INVALID'}")
    
    if result_new and not result_current:
        print("\n💡 Recommendation: Update .env with the new key")
    elif result_new:
        print("\n✅ New key works! You can use it.")

if __name__ == "__main__":
    asyncio.run(main())
