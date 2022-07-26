import argparse
import os
from pathlib import Path

import numpy as np

from oscillating_line import oscillating_line
from spectrogram import spectrogram
from trappin_scraper import download_songs, convert_mp3_to_wav, convert_mp4_to_mp3

### CLI ARGS ###
parser = argparse.ArgumentParser(description='Trappin in Japan Jukebox')
parser.add_argument('-v', '--volume', default=None)
parser.add_argument('-t', '--type', default='fft')
args = parser.parse_args()

VOLUME = args.volume
TYPE = args.type

START_URL = "https://www.youtube.com/playlist?list=PL03tCdy8gL5JvpLbxw6SsXaNDBot7b_Ok"


def get_volumes():
	files = os.listdir('audio/wav')
	return [file[:-4] for file in files]


if __name__ == '__main__':
	if not Path('audio/mp4').exists() or not len(os.listdir('audio/mp4')):
		download_songs(START_URL)

	if not Path('audio/mp3').exists() or not len(os.listdir('audio/mp3')):
		convert_mp4_to_mp3()

	if not Path('audio/wav').exists() or not len(os.listdir('audio/wav')):
		convert_mp3_to_wav()

	volumes = get_volumes()
	user_done = False
	while not user_done:
		audio_name = np.random.choice(volumes)

		if TYPE == 'basic':
			user_done = oscillating_line(audio_name)
		else:
			user_done = spectrogram(audio_name)
