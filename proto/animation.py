import animation
import time

# default animation (white, dots, default speed)
@animation.wait()
def default():
    time.sleep(10)


# clock animation (white, default speed)
clock = ["-", "\\", "|", "/"]


@animation.wait(clock)
def do_something():
    time.sleep(10)


# horizontal line animation (blue, default speed)
lines = ["   ", "-  ", "-- ", "---"]


@animation.wait(lines, color="blue")
def do_something_else():
    time.sleep(10)


# hashtag animation (cyan, slow)
tags = ["#   ", "##  ", "### ", "####"]

animation = animation.Wait(tags, color="blue", speed=0.5)
animation.start()
time.sleep(4)
animation.stop()
