import curses
import time

from utils import (
    set_up_curses,
    add_title,
    play,
    load_song,
    song_length,
    break_down_curses,
    get_max_amplitude,
    configure_display_screen,
)
from constants import GREEN, RED


def oscillating_line_display(
    amplitudes, pad, audio_length, frame_rate, max_amplitude, audio_name
):
    """Play audio while displaying amplitude of current signal"""
    height, width = pad.getmaxyx()

    # display is made up of a combination of the these full lines of '#'
    full_line_str = "".join(["#" for _ in range(int(0.6 * width))])

    s = time.time()
    # start the song
    play(audio_name)
    while (curr_time := time.time() - s) < audio_length:
        #  calculate how far into the song we are
        pad.clear()

        # we have 44k frames per second, therefore, we multiply the current time  (seconds) by the frame rate
        frame = curr_time * frame_rate

        # convert signal cache to display cache
        raw_data = amplitudes[int(frame)]
        data = abs(int(height * raw_data / max_amplitude))

        for i in range(1, data + 1):
            # red top if the amplitude is fairly large
            color = GREEN if i < height * 0.6 else RED

            # need to subtract 2 cause curses coord system sucks
            y = height - 2 - i
            y = 0 if y < 0 else y
            pad.addstr(
                y,
                int(0.2 * width),
                full_line_str,
                curses.color_pair(color) | curses.A_BOLD,
            )

        pad.refresh()
        # leave animation on screen for 1/100th of a second
        pad.timeout(10)

        if pad.getch() != -1:
            return True

    return False


def oscillating_line(audio_name):
    song, signal = load_song(audio_name)
    audio_length = song_length(song)

    # create terminal gui to display animation
    scr = set_up_curses()

    # create sub-display for volume meter
    full_height, full_width = scr.getmaxyx()
    title, pad = configure_display_screen(audio_name, full_height, full_width)

    max_amplitude = get_max_amplitude(signal, audio_name)

    # run the animation
    add_title(title, scr)
    try:
        user_done = oscillating_line_display(
            signal, pad, audio_length, song.getframerate(), max_amplitude, audio_name
        )
    except Exception as e:
        user_done = True
        print(e)
    finally:
        # need to enable terminal functionality
        break_down_curses()

    return user_done
