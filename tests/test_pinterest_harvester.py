import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

spec = importlib.util.spec_from_file_location(
    "pinterest",
    Path(__file__).resolve().parents[1] / "scripts" / "pinterest_harvester.py"
)
p_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p_mod)


class FakeResponse:
    def __init__(self, data=b"fake_jpeg_bytes", status=200):
        self.data = data
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.data


class PinterestHarvesterTests(unittest.TestCase):
    def test_upscale_url(self):
        low_res = "https://i.pinimg.com/236x/24/6c/23/246c2310c9c68cefc9553ca786095a06.jpg"
        expected = "https://i.pinimg.com/1200x/24/6c/23/246c2310c9c68cefc9553ca786095a06.jpg"
        self.assertEqual(p_mod.upscale_pinterest_url(low_res), expected)

    def test_harvest_pins_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            out_dir = tmp / "images"
            index_path = tmp / "index.json"

            harvester = p_mod.PinterestHarvester(str(out_dir), str(index_path))

            pins = [
                {
                    "hash": "abc12345",
                    "url": "https://i.pinimg.com/236x/ab/c1/23/abc12345.jpg",
                    "title": "Test Pin 1",
                    "author": "tester",
                    "tags": ["test", "tag"]
                }
            ]

            with patch("urllib.request.urlopen", return_value=FakeResponse()):
                added = harvester.harvest_pins(pins)
                self.assertEqual(added, 1)
                self.assertEqual(len(harvester.index), 1)

                # Re-running with same pin should be deduplicated
                added_again = harvester.harvest_pins(pins)
                self.assertEqual(added_again, 0)
                self.assertEqual(len(harvester.index), 1)

    def test_harvest_rss_feed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            out_dir = tmp / "images"
            index_path = tmp / "index.json"

            sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0">
              <channel>
                <title>Sample Board</title>
                <item>
                  <title>Art Reference</title>
                  <link>https://www.pinterest.com/pin/999888777/</link>
                  <description>&lt;img src="https://i.pinimg.com/236x/de/ad/be/deadbeef.jpg" /&gt;</description>
                </item>
              </channel>
            </rss>"""

            harvester = p_mod.PinterestHarvester(str(out_dir), str(index_path))

            with patch("urllib.request.urlopen") as mock_url:
                mock_url.side_effect = [
                    FakeResponse(data=sample_rss.encode("utf-8")),  # RSS request
                    FakeResponse(data=b"image_bytes")  # Image download
                ]
                added = harvester.harvest_feed("https://www.pinterest.com/user/board.rss")
                self.assertEqual(added, 1)
                self.assertEqual(len(harvester.index), 1)
                self.assertEqual(harvester.index[0]["title"], "Art Reference")
                self.assertTrue((out_dir / "pinterest_deadbeef.jpg").exists())


if __name__ == "__main__":
    unittest.main()
