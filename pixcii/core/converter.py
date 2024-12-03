import numpy as np
import cv2
from PIL import Image
from .filters import (
    ASCII_CHARS, NUM_CHARS,
    HALFTONE_CHARS, NUM_HALFTONE_CHARS,
    get_ansi_color, pixels_to_braille,
    floyd_steinberg_dither, edge_detection_to_ascii,
)

_CELL_AR = 0.5  # 0.5 лучше

# чтобы pil.image и цвкадр гонять через одни и те же ветки
def _to_bgr(src):
    if isinstance(src, Image.Image):
        return cv2.cvtColor(np.array(src.convert("RGB")), cv2.COLOR_RGB2BGR)
    return src

def _rotate_pil(image, deg):
    if deg: return image.rotate(deg, expand=True)
    return image

def _rotate_cv(frame, deg):
    # быстрые повороты для кратных 90
    if deg in (90, -270):return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if deg in (180, -180): return cv2.rotate(frame, cv2.ROTATE_180)
    if deg in (270, -90): return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if deg == 0: return frame
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2
    M = cv2.getRotationMatrix2D((cx, cy), float(deg), 1.0)
    cos = abs(M[0, 0]); sin = abs(M[0, 1])
    nw = int((h * sin) + (w * cos))
    nh = int((h * cos) + (w * sin))
    M[0, 2] += nw / 2 - cx
    M[1, 2] += nh / 2 - cy
    return cv2.warpAffine(frame, M, (nw, nh))

def _render_blocks(rgb, color):
    H, W = rgb.shape[:2]
    if H % 2:
        pad = np.zeros((1, W, 3), dtype=rgb.dtype)
        rgb = np.vstack([rgb, pad])
        H += 1

    out = []
    for y in range(0, H, 2):
        line = []
        for x in range(W):
            t = rgb[y, x]
            b = rgb[y + 1, x]
            if color:
                line.append(
                    f"\x1b[38;2;{t[0]};{t[1]};{t[2]}m"
                    f"\x1b[48;2;{b[0]};{b[1]};{b[2]}m▀"
                )
            else:
                tg = int(np.mean(t)); bg = int(np.mean(b))
                if   tg > 128 and bg > 128: line.append("█")
                elif tg > 128: line.append("▀")
                elif bg > 128: line.append("▄")
                else: line.append(" ")
        out.append("".join(line) + "\x1b[0m")
    return "\n".join(out)

def _render_braille(bgr_resized, dither, color):
    # 2x4
    th, tw = bgr_resized.shape[:2]
    gray = cv2.cvtColor(bgr_resized, cv2.COLOR_BGR2GRAY)
    if dither: binary = floyd_steinberg_dither(gray)
    else: binary = gray > np.mean(gray)

    out = []
    for y in range(0, th, 4):
        row = []
        for x in range(0, tw, 2):
            ch = pixels_to_braille(binary[y:y + 4, x:x + 2])
            if color:
                b, g, r = bgr_resized[y:y + 4, x:x + 2].mean(axis=(0, 1)).astype(int)
                row.append(f"{get_ansi_color(r, g, b)}{ch}")
            else:
                row.append(ch)
        out.append("".join(row) + ("\x1b[0m" if color else ""))
    return "\n".join(out)


def _render_chars(bgr_resized, mode, color):
    if mode == 'halftone': chars, n = HALFTONE_CHARS, NUM_HALFTONE_CHARS
    else:chars, n = ASCII_CHARS, NUM_CHARS

    h, w = bgr_resized.shape[:2]
    gray = cv2.cvtColor(bgr_resized, cv2.COLOR_BGR2GRAY)
    idx = (gray.astype(np.int32) * n // 256)

    if not color and mode != 'matrix': return "\n".join("".join(chars[r]) for r in idx)

    rgb = cv2.cvtColor(bgr_resized, cv2.COLOR_BGR2RGB)
    rows = []
    for y in range(h):
        rp, rc = rgb[y], idx[y]
        line = ""
        if mode == 'matrix':
            for p, c in zip(rp, rc):
                intensity = int(np.mean(p))
                line += f"\x1b[38;2;0;{intensity};0m{chars[c]}"
        else:
            for p, c in zip(rp, rc):
                line += f"\x1b[38;2;{p[0]};{p[1]};{p[2]}m{chars[c]}"
        rows.append(line + "\x1b[0m")
    return "\n".join(rows)

def _convert(bgr, new_width, color, mode, dither):
    if mode == 'edges': return edge_detection_to_ascii(bgr, new_width, color)

    h, w = bgr.shape[:2]
    ar = h / w

    if mode == 'blocks':
        nh = int(ar * new_width)
        if nh % 2: nh += 1
        resized = cv2.resize(bgr, (new_width, nh))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        # rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        return _render_blocks(rgb, color)

    if mode == 'braille':
        tw = new_width * 2
        th = int(ar * tw)
        tw -= tw % 2
        th -= th % 4
        if th < 4: th = 4
        resized = cv2.resize(bgr, (tw, th))
        return _render_braille(resized, dither, color)

    # дефолт + halftone + matrix
    nh = int(ar * new_width * _CELL_AR)
    resized = cv2.resize(bgr, (new_width, nh))
    return _render_chars(resized, mode, color)

def image_to_ascii(image, new_width=100, color=True, rotation=0, mode='ascii', dither=True):
    image = _rotate_pil(image, rotation)
    return _convert(_to_bgr(image), new_width, color, mode, dither)

def video_frame_to_ascii(frame, new_width=100, color=True, rotation=0, mode='ascii', dither=True):
    return _convert(_rotate_cv(frame, rotation), new_width, color, mode, dither)
