#!/usr/bin/env python3
"""Unit tests for generate_icons pipeline."""

import unittest
from pathlib import Path
from PIL import Image
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_icons import (
    extract_clover_emblem,
    build_macos_tile,
    build_macos_master_1024,
    build_windows_master_512,
)


class TestIconGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.clover_jpg = cls.root / "reference_app" / "clover-original.jpg"

    def test_extract_clover_emblem(self):
        self.assertTrue(self.clover_jpg.exists(), "clover-original.jpg must exist")
        emblem = extract_clover_emblem(self.clover_jpg)
        self.assertEqual(emblem.mode, "RGBA")
        self.assertGreater(emblem.width, 400)
        self.assertGreater(emblem.height, 400)
        # Verify alpha channel exists and contains non-transparent pixels
        alpha = emblem.split()[-1]
        extrema = alpha.getextrema()
        self.assertEqual(extrema[0], 0)
        self.assertEqual(extrema[1], 255)

    def test_build_macos_master(self):
        emblem = extract_clover_emblem(self.clover_jpg)
        master = build_macos_master_1024(emblem)
        self.assertEqual(master.size, (1024, 1024))
        self.assertEqual(master.mode, "RGBA")

    def test_build_windows_master(self):
        emblem = extract_clover_emblem(self.clover_jpg)
        win_master = build_windows_master_512(emblem)
        self.assertEqual(win_master.size, (512, 512))
        self.assertEqual(win_master.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
