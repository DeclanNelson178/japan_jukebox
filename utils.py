import curses
import numpy as np
import os
import wave
from dotenv import load_dotenv
from pathlib import Path
from playsound import playsound

# SETUP HELPERS
from song_scraper import download_songs, convert_mp4_to_mp3, convert_mp3_to_wav


def setup(url):
    # set up file structure and get songs
    if not Path(f"{os.getenv('HOME_PATH')}/audio/mp4").exists() or not len(
        os.listdir(f"{os.getenv('HOME_PATH')}/audio/mp4")
    ):
        download_songs(url)

    # convert mp4 to mp3 so that we can play audio with playsound package
    if not Path(f"{os.getenv('HOME_PATH')}/audio/mp3").exists() or not len(
        os.listdir(f"{os.getenv('HOME_PATH')}/audio/mp3")
    ):
        convert_mp4_to_mp3()

    # decode mp3 audio to analyze signal
    if not Path(f"{os.getenv('HOME_PATH')}/audio/wav").exists() or not len(
        os.listdir(f"{os.getenv('HOME_PATH')}/audio/wav")
    ):
        convert_mp3_to_wav()


# DISPLAY HELPERS
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
    """Avoid exiting program without re-enabling command line tools"""
    curses.curs_set(True)
    curses.echo()
    curses.endwin()


def add_title(title, scr):
    """Add title text to the screen"""
    scr.addstr(0, 0, title)
    scr.refresh()


def configure_display_screen(audio_name, height, width, buffer=0):
    """Add pad to screen for animation display"""
    title = audio_name.replace("_", " ")
    title_lines = 1 + buffer
    volume_height_fraction = 1 * (height - title_lines) / height

    pad = curses.newwin(int(height * volume_height_fraction), width, title_lines, 0)

    return title, pad


# AUDIO HELPERS
def play(audio_name):
    """Play mp3 file asynchronously"""
    playsound(f"{os.getenv('HOME_PATH')}/audio/mp3/{audio_name}.mp3", False)


def load_song(audio_name):
    """Read in song data"""
    song = wave.open(f"{os.getenv('HOME_PATH')}/audio/wav/{audio_name}.wav", "r")
    if song.getnchannels() == 2:
        wave.setnchannels(1)

    signal = song.readframes(-1)
    signal = np.frombuffer(signal, "int16")

    return song, signal


# COMPUTATION HELPERS
def song_length(song):
    """how long to play animation"""
    return song.getnframes() / song.getframerate()


def get_max_amplitude(signal, audio_name):
    """Largest signal in song file"""
    data_path = f"{os.getenv('HOME_PATH')}/cache/{audio_name}_max_amplitude.txt"
    if Path(data_path).exists():
        with open(data_path, "r") as file:
            max_amplitude = int(file.read())
    else:
        with open(data_path, "w") as file:
            max_amplitude = max(signal)
            file.write(str(max_amplitude))

    return max_amplitude


# SONG SELECTION HELPERS
def get_volumes():
    """Get all possible songs to play"""
    files = os.listdir(f"{os.getenv('HOME_PATH')}/audio/wav")
    return [file[:-4] for file in files]


def match_song(volume_num, songs):
    """Find song closest to provided volume number"""
    songs_and_numbers = []
    for song in songs:
        split_song = song.split("_")
        potential_number = split_song[-1]
        try:
            songs_and_numbers.append((song, int(potential_number)))
        except:
            pass

    closest_song = None
    closest_song_dist = float("inf")
    for song, num in songs_and_numbers:
        if volume_num == num:
            return song
        elif (dist := abs(volume_num - num)) < closest_song_dist:
            closest_song = song
            closest_song_dist = dist

    return closest_song
