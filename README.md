# japan_jukebox
Play 'Trappin in Japan' from terminal.

## Set Up:
Download codebase and install dependencies from `requirements.txt`. Once everything is installed,
run `python3 driver.py`
- Program begins by creating audio and cache directories in same folder as driver file
- Downloads all songs from YouTube
- Converts mp4 to mp3 to wav

## Playing Songs
Once songs are downloaded, program will choose a song at random, generate necessary data (saving to cache to speed this 
process up next time), and play audio with visual display.
- Command Line Options:
  - `-v INT`: specify the song number that you want played
    - This feature is mainly for the 'Trappin in Japan' playlist
    - Defaults to random
  - `-r BOOLEAN`: whether to play one song on repeat or shuffle through all audio
    - Defaults to false
  - `-t basic/fft`: display oscillating amplitude bar or spectogram
    - Defaults to spectogram

## Other Music
This program was written specifically for playing the different volumes of 'Trappin in Japan' on YouTube.
It can be adapted to play other playlists with minimum work. Replacing `START_URL` global
variable in driver with desired playlist URL will do the trick. Note that any previous audio and cache data
present will be overwritten. Also note that the `-v` CLI argument will no longer work.


Playlist URL: https://www.youtube.com/playlist?list=PL03tCdy8gL5JvpLbxw6SsXaNDBot7b_Ok
