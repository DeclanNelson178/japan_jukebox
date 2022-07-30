import argparse
import curses
import numpy as np
import pickle
import time
from constants import (
    DISPLAY_CHARS,
    MIN_FREQ,
    MAX_FREQ,
    RED,
    MAGENTA,
    YELLOW,
    GREEN,
    CYAN,
)
from oscillating_line import oscillating_line
from pathlib import Path
from utils import (
    load_song,
    song_length,
    set_up_curses,
    play,
    break_down_curses,
    get_max_amplitude,
    configure_display_screen,
    add_title,
)


def get_char(char_height, screen_height):
    """Which character to display depending on distance from center line"""
    if char_height >= screen_height - 1 or char_height <= 1:
        return DISPLAY_CHARS[-1]

    middle_screen = screen_height // 2
    dist = abs(middle_screen - char_height)

    char_idx = int(dist / middle_screen * len(DISPLAY_CHARS))
    return DISPLAY_CHARS[char_idx]


def sfft(signal, window_rate, audio_length):
    """Short Frame Fast Fourier Transform (no overlapping windows)"""
    num_frame_windows = window_rate * audio_length
    frames_list = np.array_split(signal, num_frame_windows)
    return [
        # abs to remove imaginary part
        abs(num)
        for num in [np.fft.fft(frames)[MIN_FREQ:MAX_FREQ] for frames in frames_list]
    ]


def scale_amplitudes(frequencies, height):
    """Convert amplitude signals to pixel heights"""
    max_freq = max(frequencies)
    max_freq = 1 if max_freq == 0 else max_freq
    return [int(height * (freq / max_freq)) for freq in frequencies]


def spectrogram_data(signal, scr, audio_length, window_rate, audio_name):
    """Convert .wav file to pixel height for varying frequency groups"""
    data_path = f"./cache/{audio_name}_sfft.bin"
    if Path(data_path).exists():
        return pickle.load(open(data_path, "rb"))

    height, width = scr.getmaxyx()
    display_data = []
    # get the frequencies present in a 1/window_rate time frame for all time frames
    for frequencies in sfft(signal, window_rate, audio_length):
        # need to group frequencies together to fit in display
        consolidated_frequencies = [
            np.mean(grouped_freqs)
            for grouped_freqs in np.array_split(frequencies, width - 2)
        ]
        display_data.append(scale_amplitudes(consolidated_frequencies, height))

    # save data in cache
    pickle.dump(display_data, open(data_path, "wb"))

    return display_data


def color_picker(amplitude_pct):
    """Color frequency group depending on amplitude"""
    if amplitude_pct > 0.6:
        return RED
    elif amplitude_pct > 0.5:
        return MAGENTA
    elif amplitude_pct > 0.4:
        return YELLOW
    elif amplitude_pct > 0.2:
        return GREEN

    return CYAN


def spectrogram_display(
    scr,
    audio_name,
    audio_length,
    frequency_data,
    frame_rate,
    amplitude_data,
    max_amplitude,
    window_rate,
):
    """Show frequency groups amplitudes"""
    height, _ = scr.getmaxyx()

    # start audio
    play(audio_name)

    # keep track of time
    s = time.time()
    while (curr_time := time.time() - s) < audio_length:
        # refresh screen
        scr.clear()

        # get data idx depending on how far into song
        idx = int(curr_time * window_rate)
        idx = len(frequency_data) - 1 if idx >= len(frequency_data) else idx

        # get frequency and amplitude, convert to display data
        frequencies = frequency_data[idx]
        frame_amplitude = amplitude_data[int(curr_time * frame_rate)]
        color = color_picker(frame_amplitude / max_amplitude)

        for x, amplitude in enumerate(frequencies):
            offset = (height - amplitude) // 2
            for i in range(0, amplitude + 1):
                # curses is weird, make sure we don't display anything off page
                y = height - 2 - i - offset
                if y > height - 2:
                    y = height - 2
                elif y < 0:
                    # y = 0 and y = 1 both cause errors
                    y = 2

                scr.addstr(
                    y,
                    x,
                    get_char(y, height - 2),
                    curses.color_pair(color) | curses.A_BOLD,
                )

        # show display
        scr.refresh()

        # wait small amount of time
        scr.timeout(int(1 / window_rate * 1000))

        # check for user interrupt
        if scr.getch() != -1:
            return True
    return False


def spectrogram(audio_name):
    # process ten sound-bites per second
    window_rate = 10

    song, signal = load_song(audio_name)
    audio_length = song_length(song)

    # create terminal gui to display animation
    scr = set_up_curses()
    height, width = scr.getmaxyx()

    # set up display with name of song
    title, pad = configure_display_screen(audio_name, height, width, buffer=3)

    # perform fft on .wav file
    frequency_data = spectrogram_data(
        signal, pad, audio_length, window_rate, audio_name
    )
    max_amplitude = get_max_amplitude(signal, audio_name)

    user_done = True
    try:
        add_title(title, scr)
        user_done = spectrogram_display(
            pad,
            audio_name,
            audio_length,
            frequency_data,
            song.getframerate(),
            signal,
            max_amplitude,
            window_rate,
        )
        break_down_curses()
    except Exception as e:
        scr.clear()
        pad.clear()
        break_down_curses()
        print("error in spectrogram_display")
        print(e)
    finally:
        break_down_curses()

    return user_done
