import argparse
import time

import numpy as np

from oscillating_line import oscillating_line
from spectrogram import spectrogram

# CLI ARGS
from utils import get_volumes, match_song, setup

parser = argparse.ArgumentParser(description="Trappin in Japan Jukebox")
parser.add_argument("-v", "--volume", default=None)
parser.add_argument("-t", "--type", default="fft")
parser.add_argument("-r", "--repeat", default=False)
args = parser.parse_args()

VOLUME = args.volume
TYPE = args.type
REPEAT = args.repeat

# Playlist URL
START_URL = "https://www.youtube.com/playlist?list=PL03tCdy8gL5JvpLbxw6SsXaNDBot7b_Ok"


if __name__ == "__main__":
    setup(START_URL)

    # get song options
    volumes = get_volumes()

    # exit when user presses a key
    user_done = False
    start_time = time.time()
    played_songs = set()
    while not user_done:
        if len(played_songs) == len(volumes):
            # reset playlist if all songs have been played
            played_songs.clear()

        # select song to begin with
        if VOLUME:
            audio_name = match_song(int(VOLUME), volumes)
            if not REPEAT:
                # avoids repeating on second loop through
                VOLUME = None
                played_songs.add(audio_name)
        else:
            # select song at random to play
            while (audio_name := np.random.choice(volumes)) in played_songs:
                continue
            played_songs.add(audio_name)

        if TYPE == "basic":
            # just amplitude
            user_done = oscillating_line(audio_name)
        else:
            # fft
            user_done = spectrogram(audio_name)

    # report session time
    total_time = time.time() - start_time
    total_minutes = total_time / 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    seconds = total_time % 60

    print(f"Time: {hours}:{minutes}:{seconds}")
