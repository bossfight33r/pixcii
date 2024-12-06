import sys
import os
from pathlib import Path

_devnull_fd = os.open(os.devnull, os.O_WRONLY)
_saved_stderr_fd = os.dup(2)
os.dup2(_devnull_fd, 2)
try:
    import argparse
    from ffpyplayer.tools import set_log_callback
    from blessed import Terminal
    from pixcii.cli.player import PixciiPlayer
    from pixcii.utils.helpers import stfu
finally:
    os.dup2(_saved_stderr_fd, 2)
    os.close(_devnull_fd)
    os.close(_saved_stderr_fd)

set_log_callback(lambda *a: None)


MODES = ('ascii', 'braille', 'edges', 'blocks', 'matrix', 'halftone')
VIDEO_EXTS = ('.mp4', '.avi', '.mov', '.mkv', '.webm')

RECENT_FILE = Path.home() / ".pixcii" / "recent"
RECENT_MAX = 10
RECENT_SHOW = 5

def _load_recent():
    try:
        if not RECENT_FILE.exists(): return []
        lines = [l.strip() for l in RECENT_FILE.read_text().splitlines() if l.strip()]
        return [p for p in lines if os.path.exists(p)][:RECENT_MAX]
    except OSError: return []

def _save_recent(path):
    try:
        rp = str(Path(path).resolve())
        items = [rp] + [x for x in _load_recent() if x != rp]
        RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECENT_FILE.write_text("\n".join(items[:RECENT_MAX]))
    except OSError: pass

def _raw_prompt(term, prompt_str, default="", choices=None):
    sys.stdout.write(prompt_str); sys.stdout.flush()
    buf = ""
    idx = -1

    def cycle(direction):
        nonlocal buf, idx
        if not choices: return
        idx = (idx + 1) % len(choices) if direction == 'up' else (idx - 1) % len(choices)
        sys.stdout.write('\b \b' * len(buf))
        buf = choices[idx]
        sys.stdout.write(buf); sys.stdout.flush()

    try:
        with term.cbreak():
            while True:
                key = term.inkey()
                if not key: continue
                if key.name in ('KEY_ENTER', 'KEY_LINEFEED'):
                    sys.stdout.write('\n'); sys.stdout.flush()
                    return buf.strip() or default
                if key.name in ('KEY_BACKSPACE', 'KEY_DELETE'):
                    if buf:
                        buf = buf[:-1]
                        sys.stdout.write('\b \b'); sys.stdout.flush()
                    continue
                if key == '\x03':  # Ctrl+C
                    sys.stdout.write('\n'); sys.stdout.flush()
                    raise KeyboardInterrupt
                if key == '\x04':  # Ctrl+D
                    sys.stdout.write('\n'); sys.stdout.flush()
                    return default
                if key.is_sequence:
                    if   key.name == 'KEY_UP':   cycle('up')
                    elif key.name == 'KEY_DOWN': cycle('down')
                    continue
                buf += key
                sys.stdout.write(key); sys.stdout.flush()
    except Exception:
        # фолбэк когда не tty
        if not sys.stdin.isatty():
            return sys.stdin.readline().rstrip('\r\n').strip() or default
        return default


def _interactive_setup(term):
    os.system('clear' if os.name != 'nt' else 'cls')
    print()
    green = "\x1b[38;2;90;255;130m"
    dim   = "\x1b[38;2;130;145;140m"
    soft  = "\x1b[38;2;180;230;200m"
    reset = "\x1b[0m"

    def ask(label, default="", choices=None):
        hint = f" {dim}[{default}]{reset}" if default else ""
        return _raw_prompt(term, f"   {green}›{reset} {label}{hint}: ", default, choices)

    recent = _load_recent()[:RECENT_SHOW]
    if recent:
        print(f"   {dim}recent  {soft}(↑/↓ to cycle){reset}")
        for i, p in enumerate(recent, 1):
            print(f"     {green}{i}{reset}  {soft}{os.path.basename(p)}{reset}  {dim}{p}{reset}")
        print()

    f = ask("Drag-drop a file, type a path, or pick #", choices=recent or None)
    if recent and f.isdigit() and 1 <= int(f) <= len(recent):
        f = recent[int(f) - 1]
    else:
        if f and f[0] == f[-1] and f[0] in ("'", '"'):
            f = f[1:-1]
        f = os.path.expanduser(f.replace('\\ ', ' '))
    if not f:
        print(f"\n   {green}✦{reset} {dim}no file, no party{reset}\n")
        sys.exit(0)
    sys.argv.append(f)

    r = ask("Rotate (0/90/180/270)", "0")
    if r.lstrip('-').isdigit() and r != "0": sys.argv += ['-r', r]

    if f.lower().endswith(VIDEO_EXTS):
        if ask("Loop? (y/N)", "N").lower() == 'y': sys.argv.append('-l')


def main():
    term = Terminal()

    if len(sys.argv) == 1:
        try:
            _interactive_setup(term)
        except KeyboardInterrupt:
            print("\n   \x1b[38;2;90;255;130m✦\x1b[0m \x1b[38;2;180;230;200mSee you space cowboy.\x1b[0m\n")
            sys.exit(0)

    p = argparse.ArgumentParser(description="PIXCII: Multithreaded Media Engine")
    p.add_argument("path", help="Path to file")
    p.add_argument("-w", "--width", type=int, help="Width")
    p.add_argument("-v", "--video", action="store_true", help="Force video")
    p.add_argument("-nc", "--no-color", action="store_true", help="Disable color")
    p.add_argument("-r", "--rotate", type=int, default=0, help="Rotation")
    p.add_argument("-fps", "--fps", type=int, default=60, help="FPS")
    p.add_argument("-m", "--mode", choices=list(MODES), help="Mode")
    p.add_argument("-na", "--no-audio", action="store_true", help="Disable audio")
    p.add_argument("-nd", "--no-dither", action="store_true", help="Disable dither")
    p.add_argument("-l", "--loop", action="store_true", help="Loop")
    args = p.parse_args()

    if not os.path.exists(args.path):
        print(f"nope, '{args.path}' not found")
        sys.exit(1)

    _save_recent(args.path)
    stfu()
    player = PixciiPlayer(args)

    ext = args.path.lower()
    if args.video or ext.endswith(VIDEO_EXTS): player.play_video()
    else: player.show_image()

if __name__ == "__main__":
    main()
