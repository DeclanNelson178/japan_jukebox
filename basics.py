"""Offline vetting harness — play one local wav through the real engine and
visualizer, no scraper, no network. Lets you verify each rung by hand:

    python basics.py                      # uses audio/wav/celsius_test.wav
    python basics.py path/to/song.wav

Move the mouse over the pane and mash keys: it must NOT freeze. Then try
space (pause), n / → (skip = quit here), ↑ ↓ (volume), q (quit).
"""

import sys

from engine import AudioEngine, load_wav
from visualizer import run


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "audio/wav/celsius_test.wav"
    signal, samplerate = load_wav(path)
    engine = AudioEngine(signal, samplerate)
    title = path.split("/")[-1].rsplit(".", 1)[0].replace("_", " ")
    run(engine, title)


if __name__ == "__main__":
    main()
