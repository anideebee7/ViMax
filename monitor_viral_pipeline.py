#!/usr/bin/env python3
"""
Monitor viral pipeline progress and alert on checkpoints with time estimates.
"""
import os
import re
import time
import glob
from datetime import datetime, timedelta
from collections import defaultdict

# Phase durations (in seconds) - typical estimates
PHASE_DURATIONS = {
    "ideation": 5,
    "script_writing": 10,
    "director_brief": 5,
    "story_development": 15,
    "character_extraction": 10,
    "character_portraits": 60,  # ~20s per character
    "script_writing_story": 15,
    "storyboard": 30,  # ~5s per shot
    "frame_generation": 120,  # ~20s per frame
    "video_generation": 300,  # ~50s per video clip
    "concatenation": 10,
}

# Checkpoint patterns
CHECKPOINTS = {
    "Auto-ideating": ("ideation", "🧠 Auto-ideation started"),
    "Writing viral-optimized script": ("script_writing", "📝 Viral script writing started"),
    "Creating viral visual brief": ("director_brief", "🎬 Director brief creation started"),
    "Initiating video production": ("video_production", "🎥 Video production initiated"),
    "Developing story": ("story_development", "📖 Story development started"),
    "Extracted.*characters": ("character_extraction", "👥 Character extraction completed"),
    "Completed character portrait": ("character_portraits", "🖼️ Character portrait generated"),
    "Writing script based on story": ("script_writing_story", "📄 Script writing started"),
    "Designing storyboard": ("storyboard", "🎨 Storyboard design started"),
    "Generated.*frame": ("frame_generation", "🖼️ Frame generated"),
    "Generated video for shot": ("video_generation", "🎬 Video clip generated"),
    "Concatenating.*videos": ("concatenation", "🔗 Video concatenation started"),
    "Pipeline Complete": ("complete", "✅ Pipeline completed!"),
}

def find_latest_log():
    """Find the most recent viral_40s_short log file."""
    logs = glob.glob("viral_40s_short_*.log")
    if not logs:
        return None
    return max(logs, key=os.path.getmtime)

def parse_log_line(line):
    """Parse a log line and extract timestamp and message."""
    # Format: 2026-01-26 13:52:38,615 - module - LEVEL - message
    match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - .*? - (\w+) - (.*)', line)
    if match:
        timestamp_str, level, message = match.groups()
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            return timestamp, level, message
        except:
            pass
    return None, None, None

def estimate_time_remaining(phase, shots_count=0, characters_count=0):
    """Estimate time remaining based on current phase."""
    base_time = PHASE_DURATIONS.get(phase, 30)
    
    # Adjust for counts
    if phase == "character_portraits":
        return base_time * max(1, characters_count)
    elif phase == "storyboard":
        return base_time * max(1, shots_count)
    elif phase == "frame_generation":
        return base_time * max(1, shots_count * 2)  # Usually 2 frames per shot
    elif phase == "video_generation":
        return base_time * max(1, shots_count)
    
    return base_time

def monitor_log(log_file, start_time=None):
    """Monitor log file and alert on checkpoints."""
    if not log_file or not os.path.exists(log_file):
        print("❌ Log file not found. Waiting for it to be created...")
        return
    
    print(f"📊 Monitoring: {log_file}")
    print(f"🕐 Started at: {start_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    seen_checkpoints = set()
    phase_start_times = {}
    last_position = 0
    
    try:
        with open(log_file, 'r') as f:
            # Go to end
            f.seek(0, 2)
            last_position = f.tell()
            
        while True:
            with open(log_file, 'r') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                last_position = f.tell()
                
                for line in new_lines:
                    timestamp, level, message = parse_log_line(line.strip())
                    if not message:
                        continue
                    
                    # Check for checkpoints
                    for pattern, (phase, checkpoint_name) in CHECKPOINTS.items():
                        if re.search(pattern, message, re.IGNORECASE):
                            checkpoint_key = f"{phase}_{checkpoint_name}"
                            
                            if checkpoint_key not in seen_checkpoints:
                                seen_checkpoints.add(checkpoint_key)
                                phase_start_times[phase] = timestamp
                                
                                # Calculate elapsed time
                                if start_time:
                                    elapsed = (timestamp - start_time).total_seconds()
                                    elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                                else:
                                    elapsed_str = "N/A"
                                
                                # Estimate remaining time
                                # Try to extract counts from message
                                shots_match = re.search(r'(\d+)\s*shot', message, re.IGNORECASE)
                                chars_match = re.search(r'(\d+)\s*character', message, re.IGNORECASE)
                                shots_count = int(shots_match.group(1)) if shots_match else 0
                                chars_count = int(chars_match.group(1)) if chars_match else 0
                                
                                remaining = estimate_time_remaining(phase, shots_count, chars_count)
                                remaining_str = f"{int(remaining // 60)}m {int(remaining % 60)}s"
                                
                                print(f"\n🔔 CHECKPOINT: {checkpoint_name}")
                                print(f"   Time: {timestamp.strftime('%H:%M:%S')}")
                                print(f"   Elapsed: {elapsed_str}")
                                print(f"   Estimated remaining: ~{remaining_str}")
                                print(f"   Phase: {phase}")
                                if shots_count > 0:
                                    print(f"   Shots: {shots_count}")
                                if chars_count > 0:
                                    print(f"   Characters: {chars_count}")
                                print("-" * 70)
                                
                                if phase == "complete":
                                    print("\n🎉 PIPELINE COMPLETED!")
                                    return
            
            time.sleep(2)  # Check every 2 seconds
            
    except KeyboardInterrupt:
        print("\n\n⏹️ Monitoring stopped by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    log_file = find_latest_log()
    if log_file:
        # Try to find start time from log
        with open(log_file, 'r') as f:
            first_line = f.readline()
            start_time, _, _ = parse_log_line(first_line)
        
        monitor_log(log_file, start_time)
    else:
        print("❌ No log file found. Make sure the pipeline is running.")
        print("   Looking for: viral_40s_short_*.log")
