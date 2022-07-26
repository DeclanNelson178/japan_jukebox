import argparse
import curses
import pickle
import time
from pathlib import Path

import numpy as np

from oscillating_line import oscillating_line
from utils import load_song, song_length, set_up_curses, play, break_down_curses, get_max_amplitude, \
    configure_display_screen, add_title

### CLI ARGS ###
parser = argparse.ArgumentParser(description='Trappin in Japan Jukebox')
parser.add_argument('-v', '--volume', default=15)
parser.add_argument('-t', '--type', default='fft')
args = parser.parse_args([])

VOLUME = args.volume
TYPE = args.type

MIN_FREQ, MAX_FREQ = 30, 200

CHARS = ["s", "S", "$"]
CHARS.reverse()


def get_char(char_height, screen_height):
    if char_height >= screen_height - 1 or char_height <= 1:
        return CHARS[-1]

    middle_screen = screen_height // 2
    dist = abs(middle_screen - char_height)

    char_idx = int(dist / middle_screen * len(CHARS))
    return CHARS[char_idx]


def sfft(signal, window_rate, audio_length):
    num_frame_windows = window_rate * audio_length
    frames_list = np.array_split(signal, num_frame_windows)
    return[
        # abs to remove imaginary part
        abs(num) for num in [
            np.fft.fft(frames)[MIN_FREQ:MAX_FREQ] for frames in frames_list
        ]
    ]


def scale_amplitudes(frequencies, height):
    max_freq = max(frequencies)
    max_freq = 1 if max_freq == 0 else max_freq
    return [int(height * (freq / max_freq)) for freq in frequencies]


def spectrogram_data(signal, scr, audio_length, window_rate, audio_name):
    data_path = f'./cache/{audio_name}_sfft.bin'
    if Path(data_path).exists():
        return pickle.load(open(data_path, 'rb'))

    height, width = scr.getmaxyx()
    display_data = []
    # get the frequencies present in a 1/window_rate time frame for all time frames
    for frequencies in sfft(signal, window_rate, audio_length):
        # need to group frequencies together to fit in display
        consolidated_frequencies = [
            np.mean(grouped_freqs) for grouped_freqs in np.array_split(frequencies, width - 2)
        ]
        display_data.append(scale_amplitudes(consolidated_frequencies, height))

    pickle.dump(display_data, open(data_path, 'wb'))

    return display_data


def color_picker(amplitude_pct):
    if amplitude_pct > .6:
        # red
        return 1
    elif amplitude_pct > .5:
        # magenta
        return 2
    elif amplitude_pct > .4:
        return 3
    elif amplitude_pct > .2:
        return 4

    return 5


def spectrogram_display(
        scr, audio_name, audio_length, frequency_data, frame_rate, amplitude_data, max_amplitude, window_rate
):
    height, _ = scr.getmaxyx()
    play(audio_name)
    s = time.time()
    while (curr_time := time.time() - s) < audio_length:
        scr.clear()

        idx = int(curr_time * window_rate)
        idx = len(frequency_data) - 1 if idx >= len(frequency_data) else idx

        frequencies = frequency_data[idx]
        frame_amplitude = amplitude_data[int(curr_time * frame_rate)]
        color = color_picker(frame_amplitude / max_amplitude)

        for x, amplitude in enumerate(frequencies):
            offset = (height - amplitude) // 2
            for i in range(0, amplitude + 1):
                y = height - 2 - i - offset
                if y > height - 2:
                    y = height - 2
                elif y < 0:
                    y = 2

                scr.addstr(y, x, get_char(y, height - 2), curses.color_pair(color) | curses.A_BOLD)

        scr.refresh()
        scr.timeout(int(1 / window_rate * 1000))
        if scr.getch() != -1:
            return True
    return False


def spectrogram(audio_name):
    if TYPE == 'basic':
        oscillating_line(audio_name)
    window_rate = 10

    song, signal = load_song(audio_name)
    audio_length = song_length(song)

    # create terminal gui to display animation
    scr = set_up_curses()
    height, width = scr.getmaxyx()

    title, pad = configure_display_screen(audio_name, height, width, buffer=3)

    frequency_data = spectrogram_data(signal, pad, audio_length, window_rate, audio_name)
    max_amplitude = get_max_amplitude(signal, audio_name)

    user_done = True
    try:
        add_title(title, scr)
        s = time.time()
        user_done = spectrogram_display(
            pad,
            audio_name,
            audio_length,
            frequency_data,
            song.getframerate(),
            signal,
            max_amplitude,
            window_rate
        )
        break_down_curses()
        print(f'Time taken: {time.time() - s}')
    except Exception as e:
        scr.clear()
        pad.clear()
        break_down_curses()
        print('error in spectrogram_display')
        print(e)
    finally: break_down_curses()

    return user_done

