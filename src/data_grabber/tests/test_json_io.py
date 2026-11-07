import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from libs.json_io_lib import write_json_atomic


class WriteJsonAtomicTests(unittest.TestCase):
    def test_writes_json_and_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'shared' / 'vmforum_members.json'

            write_json_atomic(path, [{'id': 1, 'name': 'Müller'}])

            with path.open(encoding='utf-8') as data_file:
                self.assertEqual(json.load(data_file), [{'id': 1, 'name': 'Müller'}])

    def test_replaces_existing_file_without_leaving_temp_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'vmforum_members.json'
            path.write_text('[{"id": 1}]', encoding='utf-8')

            write_json_atomic(path, [{'id': 2}])
            write_json_atomic(path, [{'id': 3}])

            with path.open(encoding='utf-8') as data_file:
                self.assertEqual(json.load(data_file), [{'id': 3}])
            self.assertEqual(sorted(p.name for p in Path(temp_dir).iterdir()), ['vmforum_members.json'])

    @unittest.skipIf(os.name == 'nt', 'POSIX permissions are not available on Windows')
    def test_written_file_is_readable_by_web_server(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'vmforum_members.json'

            write_json_atomic(path, [])

            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_failed_serialization_keeps_previous_file_and_removes_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'vmforum_members.json'
            path.write_text('[{"id": 1}]', encoding='utf-8')

            with self.assertRaises(TypeError):
                write_json_atomic(path, [{'id': object()}])

            self.assertEqual(path.read_text(encoding='utf-8'), '[{"id": 1}]')
            self.assertEqual(sorted(p.name for p in Path(temp_dir).iterdir()), ['vmforum_members.json'])


if __name__ == '__main__':
    unittest.main()
