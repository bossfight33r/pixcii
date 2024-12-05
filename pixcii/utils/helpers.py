import os
import sys

def stfu():
    try:
        fd = sys.stderr.fileno()
        dn = os.open(os.devnull, os.O_WRONLY)
        os.dup2(dn, fd)
    except Exception: pass

def format_time(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"
