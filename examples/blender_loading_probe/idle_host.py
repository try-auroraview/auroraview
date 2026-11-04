"""Blender-only CPU baseline for the retained resource acceptance run."""

import argparse
import json
import sys
import time
from pathlib import Path

import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=float, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
args.output.parent.mkdir(parents=True, exist_ok=True)
started = time.monotonic()


def log(event):
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps({"event": event, "elapsed_seconds": time.monotonic() - started}) + "\n"
        )


def tick():
    if time.monotonic() - started < args.seconds:
        return 1.0
    log("closed")
    bpy.ops.wm.quit_blender()
    return None


log("idle_stable")
bpy.app.timers.register(tick, first_interval=1.0)
