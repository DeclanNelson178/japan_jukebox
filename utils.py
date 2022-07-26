import curses
import wave
from pathlib import Path
import multiprocessing

import pyfiglet
from playsound import playsound

import numpy as np


def set_up_curses():
	scr = curses.initscr()
	curses.noecho()
	curses.curs_set(False)

	# handle display colors
	curses.start_color()
	curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
	curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
	curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
	curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)
	scr.clear

	return scr


def break_down_curses():
	# avoid exiting program without re-enabling command line tools
	curses.curs_set(True)
	curses.echo()
	curses.endwin()


def add_title(title, scr):
	scr.addstr(0, 0, title)
	scr.refresh()


def play(audio_name):
	# false makes the playsound asynchronous
	playsound(f'audio/mp3/{audio_name}.mp3', False)


def load_song(audio_name):
	song = wave.open(f'audio/wav/{audio_name}.wav', 'r')
	if song.getnchannels() == 2:
		wave.setnchannels(1)

	signal = song.readframes(-1)
	signal = np.frombuffer(signal, "int16")

	return song, signal


def song_length(song):
	# how long to play animation
	return song.getnframes() / song.getframerate()


def configure_display_screen(audio_name, height, width, buffer=0):
	title = audio_name.replace('_', ' ')
	title_lines = 1 + buffer
	volume_height_fraction = 1 * (height - title_lines) / height

	pad = curses.newwin(
		int(height * volume_height_fraction),
		width,
		title_lines,
		0
	)

	return title, pad


def get_max_amplitude(signal, audio_name):
	data_path = f'cache/{audio_name}_max_amplitude.txt'
	if Path(data_path).exists():
		with open(data_path, 'r') as file:
			max_amplitude = int(file.read())
	else:
		with open(data_path, 'w') as file:
			max_amplitude = max(signal)
			file.write(str(max_amplitude))

	return max_amplitude
