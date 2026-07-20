import argparse
import os
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from engine import AudioEngine, load_wav
from utils import get_volumes, match_song, setup
from visualizer import PALETTE_ORDER, run

load_dotenv()
load_dotenv(dotenv_path=Path(".") / ".env")

BASE = os.getenv("HOME_PATH") or os.path.dirname(os.path.abspath(__file__))

# Playlist URL
START_URL = "https://www.youtube.com/playlist?list=PL03tCdy8gL5JvpLbxw6SsXaNDBot7b_Ok"


def parse_args():
    parser = argparse.ArgumentParser(description="Trappin in Japan Jukebox")
    parser.add_argument("-v", "--volume", default=None, help="song number to play")
    parser.add_argument("-r", "--repeat", default=False, help="repeat one song")
    parser.add_argument(
        "-p", "--palette", default="trap", choices=PALETTE_ORDER,
        help="color palette",
    )
    # accepted for backward compatibility; the visualizer is now unified
    parser.add_argument("-t", "--type", default=None, help=argparse.SUPPRESS)
    return parser.parse_args()


def pick_song(volumes, played, volume_arg):
    if volume_arg:
        return match_song(int(volume_arg), volumes)
    while (choice := np.random.choice(volumes)) in played:
        continue
    return choice


def main():
    args = parse_args()
    setup(START_URL)
    volumes = get_volumes()

    played = set()
    start_time = time.time()
    volume_arg = args.volume

    while True:
        if len(played) == len(volumes):
            played.clear()

        audio_name = pick_song(volumes, played, volume_arg)
        played.add(audio_name)
        if not args.repeat:
            volume_arg = None  # only honor -v on the first song

        signal, samplerate = load_wav(f"{BASE}/audio/wav/{audio_name}.wav")
        engine = AudioEngine(signal, samplerate)
        title = audio_name.replace("_", " ")

        quit_session = run(engine, title, palette_name=args.palette)
        if quit_session:
            break

    total = time.time() - start_time
    print(f"Played for {int(total // 60)}m {int(total % 60)}s. Stay trappin.")


if __name__ == "__main__":
    main()
