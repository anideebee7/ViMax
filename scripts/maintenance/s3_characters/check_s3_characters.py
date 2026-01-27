#!/usr/bin/env python3
"""Check and update S3 character structure"""
import subprocess
import json
import tempfile
import os

def run_s3_cmd(*args):
    """Run AWS S3 command"""
    result = subprocess.run(
        ["aws", "s3", *args],
        capture_output=True,
        text=True
    )
    return result.returncode == 0, result.stdout, result.stderr

def get_json_from_s3(s3_path):
    """Download and parse JSON from S3"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name
    try:
        result = subprocess.run(
            ["aws", "s3", "cp", s3_path, temp_path],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return None
        with open(temp_path, "r") as f:
            return json.load(f)
    except:
        return None
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def main():
    bucket = "intelli-verse-x-media"
    prefix = "agent-assets/brands/intelli-verse-x/Characters"
    
    # List character folders
    success, output, error = run_s3_cmd("ls", f"s3://{bucket}/{prefix}/")
    print("=== Character Folders ===")
    print(output if success else f"Error: {error}")
    
    # Extract folder names
    folders = []
    if success:
        for line in output.strip().split('\n'):
            if 'PRE' in line:
                folder = line.split()[-1].rstrip('/')
                folders.append(folder)
    
    print(f"\nFound folders: {folders}")
    
    # Check each folder for character.json
    print("\n=== Character Details ===")
    for folder in folders:
        char_json = get_json_from_s3(f"s3://{bucket}/{prefix}/{folder}/character.json")
        if char_json:
            print(f"\n{folder}:")
            print(f"  ID: {char_json.get('id')}")
            print(f"  Name: {char_json.get('name')}")
            print(f"  Identifier: {char_json.get('identifier_in_scene', 'N/A')}")
            print(f"  Aliases: {char_json.get('aliases', [])}")
        else:
            print(f"\n{folder}: No character.json found")

if __name__ == "__main__":
    main()
