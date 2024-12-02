import numpy as np
from PIL import Image
import cv2

# градиент от тёмного к светлому
ASCII_CHARS = np.array(list("@%#*+=-:. "))
NUM_CHARS = len(ASCII_CHARS)
HALFTONE_CHARS = np.array(list("◉●•· "))
NUM_HALFTONE_CHARS = len(HALFTONE_CHARS)

def get_ansi_color(r, g, b):
    return f"\x1b[38;2;{r};{g};{b}m"

_BRAILLE_BITS = np.array([
    [  1,   8],
    [  2,  16],
    [  4,  32],
    [ 64, 128],
], dtype=np.uint16)


def pixels_to_braille(pixels_binary):
    code = int((pixels_binary.astype(np.uint16) * _BRAILLE_BITS).sum())
    return chr(0x2800 + code)

_FS_DITHER = getattr(Image, 'Dither', Image).FLOYDSTEINBERG

def floyd_steinberg_dither(image_gray):
    pil = Image.fromarray(np.ascontiguousarray(image_gray, dtype=np.uint8), mode='L')
    return np.array(pil.convert('1', dither=_FS_DITHER), dtype=bool)

_EDGE_THRESHOLD = 50

def edge_detection_to_ascii(frame, new_width=100, color=True):
    h, w = frame.shape[:2]
    new_height = int((h / w) * new_width * 0.5)
    resized = cv2.resize(frame, (new_width, new_height))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    sx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag, ang = cv2.cartToPolar(sx, sy, angleInDegrees=True)
    mask = mag > _EDGE_THRESHOLD

    out = []
    for y in range(new_height):
        row = []
        for x in range(new_width):
            if not mask[y, x]:
                row.append(" ")
                continue
            a = ang[y, x]
            # 4 направления вертикаль/диагональ/горизонталь/диагональ
            if   (0 <= a < 22.5)   or (157.5 <= a < 202.5) or (337.5 <= a <= 360): ch = "|"
            elif (22.5 <= a < 67.5) or (202.5 <= a < 247.5):                       ch = "/"
            elif (67.5 <= a < 112.5) or (247.5 <= a < 292.5):                      ch = "-"
            else:                                                                  ch = "\\"
            if color:
                b, g, r = resized[y, x]
                row.append(f"{get_ansi_color(r, g, b)}{ch}")
            else: row.append(ch)
        out.append("".join(row) + ("\x1b[0m" if color else ""))
    return "\n".join(out)
