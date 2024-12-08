import numpy as np
from PIL import Image
import pytest
from pixcii.core.converter import image_to_ascii, video_frame_to_ascii

def test_image_to_ascii_basic():
    img = Image.new('RGB', (10, 10), color=(255, 255, 255))
    ascii_str = image_to_ascii(img, new_width=10, mode='ascii', color=False)
    assert len(ascii_str.split('\n')) > 0
    assert ' ' in ascii_str

def test_video_frame_to_ascii_basic():
    frame = np.full((10, 10, 3), 255, dtype=np.uint8)
    ascii_str = video_frame_to_ascii(frame, new_width=10, mode='ascii', color=False)
    assert len(ascii_str.split('\n')) > 0
    assert ' ' in ascii_str

def test_braille_mode():
    img = Image.new('RGB', (2, 4), color=(0, 0, 0))
    img.putpixel((0, 0), (255, 255, 255))
    ascii_str = image_to_ascii(img, new_width=1, mode='braille', color=False)
    assert '⠁' in ascii_str

def test_blocks_mode():
    img = Image.new('RGB', (2, 2), color=(255, 255, 255))
    ascii_str = image_to_ascii(img, new_width=2, mode='blocks', color=False)
    assert '█' in ascii_str
