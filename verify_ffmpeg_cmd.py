# Developed by ARGON telegram: @REACTIVEARGON
import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from bot.func.ffmpeg_utils import generate_ffmpeg_cmd

def test_generate_ffmpeg_cmd():
    settings = {
        "video": {
            "resolution": ["1080p"],
            "codec": "libx264",
            "crf": 23,
            "preset": "medium"
        }
    }
    input_file = "test_input.mp4"
    output_base = "test_output"

import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from bot.func.ffmpeg_utils import generate_ffmpeg_cmd

def test_generate_ffmpeg_cmd():
    settings = {
        "video": {
            "resolution": ["1080p"],
            "codec": "libx264",
            "crf": 23,
            "preset": "medium"
        }
    }
    input_file = "test_input.mp4"
    output_base = "test_output"

    commands = generate_ffmpeg_cmd(settings, input_file, output_base)

    for cmd_info in commands:
        cmd = cmd_info["cmd"]
        print(f"Generated command: {cmd}")

        # Check for map flags, handling potential quotes
        has_video = "-map 0:v?" in cmd or "-map '0:v?'" in cmd or '-map "0:v?"' in cmd
        has_audio = "-map 0:a?" in cmd or "-map '0:a?'" in cmd or '-map "0:a?"' in cmd
        has_subs = "-map 0:s?" in cmd or "-map '0:s?'" in cmd or '-map "0:s?"' in cmd

        if has_video and has_audio and has_subs:
            print("SUCCESS: Command contains correct map flags.")
        else:
            print("FAILURE: Command missing correct map flags.")
            sys.exit(1)

        if "-map 0 " in cmd or "-map '0'" in cmd: # Check for the old flag
             print("FAILURE: Command contains old map flag '-map 0'.")
             sys.exit(1)

if __name__ == "__main__":
    test_generate_ffmpeg_cmd()
