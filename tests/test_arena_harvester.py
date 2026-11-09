import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('arena', Path(__file__).resolve().parents[1] / 'scripts' / 'arena_harvester.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

class Response:
    def __init__(self, body, content_type='image/png'):
        from email.message import Message
        self.body = body
        self.headers = Message()
        self.headers['Content-Type'] = content_type
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size=-1):
        if size < 0: size = len(self.body)
        value, self.body = self.body[:size], self.body[size:]
        return value

class HarvesterTests(unittest.TestCase):
    def test_pagination_metadata_duplicates_and_restarts(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); output = root / 'images' / 'Референсы'; index = root / 'archive_index.json'
            block = {'id': 42, 'class': 'Image', 'title': 'Тест', 'description': 'Свет', 'user': {'username': 'artist'}, 'source': {'url': 'https://example.com'}, 'image': {'original': {'url': 'https://cdn.example/image'}}}
            pages = {1: [block], 2: [dict(block, id=43, **{'class':'Link'})], 3: []}
            with patch.object(a, 'fetch_page', side_effect=lambda c,p,t: pages[p]) as fetch, patch.object(a, 'urlopen', side_effect=lambda *args, **kwargs: Response(b'png bytes')) as request:
                self.assertEqual(a.harvest('minimal-typography', output, index), 0)
                self.assertEqual(fetch.call_count, 3); self.assertEqual(request.call_count, 2)
                saved = json.loads(index.read_text()); self.assertEqual(len(saved), 2)
                self.assertEqual(saved[0]['canonical_url'], 'https://www.are.na/block/42')
                self.assertEqual(saved[0]['local_path'], 'images/Референсы/arena_minimal-typography_42.png')
                self.assertIn('https://example.com', saved[0]['observation'])
                self.assertTrue((root / saved[0]['local_path']).exists())
                self.assertEqual(a.harvest('minimal-typography', output, index), 0)
                self.assertEqual(request.call_count, 2)
    def test_corrupt_index_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); index = root/'index.json'; index.write_text('{broken')
            with self.assertRaises(ValueError): a.harvest('channel', root/'images', index)
            self.assertEqual(index.read_text(), '{broken')
    def test_auth_only_sent_to_api(self):
        with patch.object(a, 'urlopen', return_value=Response(b'{"contents": []}', 'application/json')) as request:
            self.assertEqual(a.fetch_page('hello', 1, 'secret'), [])
            self.assertEqual(request.call_args.args[0].get_header('Authorization'), 'Bearer secret')
    def test_existing_unindexed_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); output = root/'images'; output.mkdir(); original = output/'arena_demo_1.jpg'; original.write_bytes(b'original')
            block = {'id':1, 'class':'Image', 'image':{'original':{'url':'https://example.com/a'}}}
            with patch.object(a, 'fetch_page', side_effect=[[block], []]), patch.object(a, 'urlopen') as request:
                self.assertEqual(a.harvest('demo', output, root/'index.json'), 0)
                request.assert_not_called(); self.assertEqual(original.read_bytes(), b'original')
if __name__ == '__main__': unittest.main()
