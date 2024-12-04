import sys
import os
import threading
import time
import queue
import shutil
import signal

from blessed import Terminal
import cv2
import numpy as np
from ffpyplayer.player import MediaPlayer
from PIL import Image

from pixcii.core.converter import video_frame_to_ascii, image_to_ascii
from pixcii.utils.helpers import format_time
from pixcii.utils.config import load_dotconfig

MODES = ('ascii', 'braille', 'edges', 'blocks', 'matrix', 'halftone')
SIDEBAR_GAP = 2  # отступ между ascii-кадром и боковой панелью

AV_DRIFT_TOLERANCE = 0.15

_C = {
    'box':    "\x1b[38;2;75;115;95m",
    'active': "\x1b[1;38;2;130;255;170m",
    'label':  "\x1b[1;38;2;180;230;200m",
    'dim':    "\x1b[38;2;130;145;140m",
    'green':  "\x1b[38;2;90;255;130m",
    'text':   "\x1b[38;2;200;225;210m",
    'soft':   "\x1b[38;2;180;230;200m",
    'accent': "\x1b[38;2;255;215;130m",
    'pause':  "\x1b[1;38;2;255;120;140m",
    'play':   "\x1b[1;38;2;90;255;130m",
    'mode':   "\x1b[1;38;2;230;245;235m",
    'bardim': "\x1b[38;2;80;95;90m",
    'bartip': "\x1b[38;2;180;255;200m",
}
_GOODBYE = "\n   \x1b[38;2;90;255;130m✦\x1b[0m \x1b[38;2;180;230;200mSee you space cowboy.\x1b[0m\n"

class PixciiPlayer:
    def __init__(self, args):
        self.args = args
        self.config = load_dotconfig()
        self.term = Terminal()

        self.use_color  = not getattr(args, 'no_color', False)
        self.use_dither = not getattr(args, 'no_dither', False)
        self.current_mode = args.mode or self.config.get('default_mode', 'ascii')
        self.width = args.width or self.config.get('default_width') or self._auto_width()

        self.paused = False
        self.running = True
        self.frame_queue = queue.Queue(maxsize=60)
        # self.frame_queue = queue.Queue(maxsize=120)
        self.reset_master_clock = False
        self.total_duration = 0
        self.notification = "ready when you are"
        self.notification_time = time.time() + 3

        if hasattr(signal, 'SIGWINCH'):
            signal.signal(signal.SIGWINCH, self._handle_sigwinch)

    @staticmethod
    def _auto_width():
        cols, _ = shutil.get_terminal_size((100, 30))
        # -18 запас под сайдбар
        return max(40, cols - 18)

    def _handle_sigwinch(self, signum, frame):
        if self.args.width:
            return
        self.width = self._auto_width()
        sys.stdout.write(self.term.clear); sys.stdout.flush()
        self._notify(f"Resized to {self.width} columns")

    def _notify(self, msg):
        self.notification = msg
        self.notification_time = time.time() + 2.5

    def _set_terminal_title(self, title):
        sys.stdout.write(f"\x1b]2;📺 Now showing: {title}\x07")

    def _playback_title(self):
        return f"PIXCII: {os.path.basename(self.args.path)}"

    def _get_key(self):
        k = self.term.inkey(timeout=0)
        return str(k) if k else None

    def restore_terminal(self):
        sys.stdout.write(self.term.normal + "\x1b]2;Terminal\x07\n")
        sys.stdout.flush()

    def _draw_sidebar(self):
        col = self.width + SIDEBAR_GAP
        c = _C
        R = self.term.normal

        def at(row, body):
            return f"{self.term.move_xy(col, row - 1)}{self.term.clear_eol}{body}"

        rows = [at(1, f"{c['box']}╭{R} {c['label']}VIBE{R} {c['box']}───────╮{R}")]
        for i, m in enumerate(MODES, 1):
            active = (m == self.current_mode)
            marker = "●" if active else "○"
            body = f"{marker} {i} {m}".ljust(12)
            color = c['active'] if active else c['dim']
            rows.append(at(i + 1, f"{c['box']}│{R}{color}{body}{R}{c['box']}│{R}"))
        rows.append(at(len(MODES) + 2, f"{c['box']}╰─────────────╯{R}"))

        base = len(MODES) + 4
        rows.append(at(base, f"{c['box']}╭{R} {c['label']}COMMANDS{R} {c['box']}──╮{R}"))
        keys = (
            ("space", "pause"),
            ("1-6",   "mode"),
            ("m",     "next"),
            ("c",     "color"),
            ("q",     "quit"),
        )
        for j, (k, lab) in enumerate(keys, 1):
            body = f" {k} {lab}".ljust(12)
            rows.append(at(base + j, f"{c['box']}│{R}{c['dim']}{body}{R}{c['box']}│{R}"))
        rows.append(at(base + len(keys) + 1, f"{c['box']}╰────────────╯{R}"))
        return "".join(rows)

    def _get_status_bar(self, current_time):
        c = _C
        R = self.term.normal
        bar_width = 28

        progress = min(1.0, current_time / self.total_duration) if self.total_duration > 0 else 0
        filled = int(bar_width * progress)
        if filled >= bar_width:
            bar = f"{c['green']}{'━' * bar_width}{R}"
        elif filled > 0:
            bar = f"{c['green']}{'━' * (filled - 1)}{c['bartip']}╸{R}{c['bardim']}{'─' * (bar_width - filled)}{R}"
        else:
            bar = f"{c['bardim']}{'─' * bar_width}{R}"

        state = f"{c['pause']}⏸ PAUSE{R}" if self.paused else f"{c['play']}▶ PLAY {R}"
        tstr  = f"{c['text']}{format_time(current_time)}{R} {c['dim']}/{R} {c['text']}{format_time(self.total_duration)}{R}"
        mstr  = f"{c['mode']}{self.current_mode.upper()}{R}"
        cdot  = f"{c['green']}●{R}" if self.use_color else f"{c['dim']}○{R}"
        sep   = f"  {c['dim']}·{R}  "

        line1 = f" {state}  {bar}  {tstr}{sep}{mstr}{sep}{cdot} {c['dim']}color{R}"
        line2 = f"   {c['accent']}✦{R} {c['text']}{self.notification}{R}" if time.time() < self.notification_time else ""
        return f"\n{line1}{self.term.clear_eol}\n{line2}{self.term.clear_eol}"

    def _render(self, frame_or_img, pts, is_video):
        if is_video:
            body = video_frame_to_ascii(
                frame_or_img, new_width=self.width, color=self.use_color,
                rotation=self.args.rotate, mode=self.current_mode, dither=self.use_dither,
            )
        else:
            body = image_to_ascii(
                frame_or_img, new_width=self.width, color=self.use_color,
                rotation=self.args.rotate, mode=self.current_mode, dither=self.use_dither,
            )
        sys.stdout.write(self.term.home + body + self._get_status_bar(pts) + self._draw_sidebar())
        sys.stdout.flush()

    def _process_key(self, key, player):
        if key in ('q', '\x1b'):
            self.running = False
            return False
        if key == ' ':
            self.paused = not self.paused
            if player: player.toggle_pause()
            self._notify("paused" if self.paused else "back")
        elif key == 'c':
            self.use_color = not self.use_color
            self._notify("color on" if self.use_color else "color off")
        elif key == 'm':
            i = MODES.index(self.current_mode)
            self.current_mode = MODES[(i + 1) % len(MODES)]
            self._notify(f"mode -> {self.current_mode}")
        elif key in '123456':
            nm = MODES[int(key) - 1]
            if nm != self.current_mode:
                self.current_mode = nm
                self._notify(f"mode -> {nm}")
        return True

    def _handle_input(self, player):
        k = self._get_key()
        if not k:
            return True
        return self._process_key(k, player)

    def _video_reader(self, cap):
        # отдельный поток на чтение иначе декодер тормозит мейн цикл
        while self.running:
            if self.paused:
                time.sleep(0.05); continue
            if self.frame_queue.full():
                time.sleep(0.01); continue
            ret, frame = cap.read()
            if not ret:
                if self.args.loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.reset_master_clock = True
                    continue
                self.frame_queue.put(None)
                break
            v_pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            self.frame_queue.put((frame, v_pts))

    def play_video(self):
        cap = cv2.VideoCapture(self.args.path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps > 0:
            self.total_duration = frame_count / fps

        player = None
        if not getattr(self.args, 'no_audio', False):
            player = MediaPlayer(self.args.path, ff_opts={'loglevel': 'quiet'})

        sys.stdout.write(self.term.clear)
        self._set_terminal_title(self._playback_title())
        threading.Thread(target=self._video_reader, args=(cap,), daemon=True).start()

        start_time = time.time()
        try:
            with self.term.cbreak(), self.term.hidden_cursor():
                while self.running:
                    if not self._handle_input(player):
                        break

                    if self.reset_master_clock:
                        if player: player.seek(0, relative=False)
                        start_time = time.time()
                        self.reset_master_clock = False
                        while not self.frame_queue.empty():
                            self.frame_queue.get()

                    try:
                        data = self.frame_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if data is None:
                        break
                    frame, video_time = data

                    if player:
                        # синк по аудио
                        player.get_frame()
                        audio_time = player.get_pts()
                        current_pts = audio_time
                        if video_time > audio_time:
                            time.sleep(video_time - audio_time)
                        elif video_time + AV_DRIFT_TOLERANCE < audio_time:
                            # self._dbg_frames += 1
                            continue
                    else:
                        elapsed = time.time() - start_time
                        current_pts = video_time
                        if video_time > elapsed:
                            time.sleep(video_time - elapsed)

                    self._render(frame, current_pts, is_video=True)

                    if self.paused:
                        self._set_terminal_title("PIXCII [PAUSED]")
                        while self.paused and self.running:
                            k = self._get_key()
                            if not k:
                                time.sleep(0.05); continue
                            self._process_key(k, player)
                            if not self.running:
                                break
                            if not self.paused:
                                self._set_terminal_title(self._playback_title())
                            self._render(frame, current_pts, is_video=True)
        finally:
            self.running = False
            cap.release()
            if player: player.close_player()
            self.restore_terminal()
            print(_GOODBYE)

    def show_image(self):
        try:
            img = Image.open(self.args.path)
            print(image_to_ascii(
                img, new_width=self.width, color=self.use_color,
                rotation=self.args.rotate, mode=self.current_mode, dither=self.use_dither,
            ))
        except Exception as e:
            print(f"failed: {e}")
