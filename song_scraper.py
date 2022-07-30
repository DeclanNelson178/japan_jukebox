import os
import subprocess
import time

from pytube import Playlist


def convert_mp4_to_mp3():
    subprocess.call(["mkdir", "-p", "audio/mp3"])
    files = subprocess.getoutput("cd audio/mp4 && ls").split("\n")
    for file in files:
        title = file[: file.find(".mp4")]
        os.system(f'cd audio/mp4 && ffmpeg -i {file} ../mp3/{title + ".mp3"}')


def convert_mp3_to_wav():
    subprocess.call(["mkdir", "-p", "audio/wav"])
    files = subprocess.getoutput("cd audio/mp3 && ls").split("\n")
    for file in files:
        title = file[: file.find(".mp3")]
        os.system(f'cd audio/mp3 && ffmpeg -i {file} -ac 1 ../wav/{title + ".wav"}')


def download_songs(base_url):
    p = Playlist(base_url)
    os.system("mkdir -p audio/mp4")

    for video in p.videos:
        print(f"Downloading: {video.title}...")
        title = "_".join(video.title.split(" ")) + ".mp4"
        try:
            video.streams.get_audio_only("mp4").download("audio/mp4", title)
        except Exception as e:
            print(f"error: {e}")
        time.sleep(5)
