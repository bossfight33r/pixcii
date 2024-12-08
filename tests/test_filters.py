import numpy as np
import pytest
from pixcii.core.filters import pixels_to_braille, floyd_steinberg_dither, get_ansi_color

def test_pixels_to_braille():
    pixels = np.zeros((4, 2), dtype=bool)
    assert pixels_to_braille(pixels) == chr(0x2800)
    pixels = np.zeros((4, 2), dtype=bool)
    pixels[0, 0] = True
    assert pixels_to_braille(pixels) == chr(0x2801)
    pixels = np.ones((4, 2), dtype=bool)
    assert pixels_to_braille(pixels) == chr(0x28FF)

def test_get_ansi_color():
    assert get_ansi_color(255, 128, 64) == "\x1b[38;2;255;128;64m"

def test_floyd_steinberg_dither():
    gray = np.full((10, 10), 128, dtype=np.uint8)
    binary = floyd_steinberg_dither(gray)

    assert binary.shape == (10, 10)
    assert binary.dtype == bool
    assert np.any(binary)
    assert not np.all(binary)
