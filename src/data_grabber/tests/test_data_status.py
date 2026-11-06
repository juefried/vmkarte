import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from libs.data_status_lib import build_data_status, write_data_status


class BuildDataStatusTests(unittest.TestCase):
    def test_contains_member_count_and_iso_offset(self):
        generated_at = datetime(2026, 11, 6, 3, 33, 0, tzinfo=timezone(timedelta(hours=1)))

        status = build_data_status(3167, generated_at)

        self.assertEqual(status['memberCount'], 3167)
        self.assertEqual(status['generatedAt'], '2026-11-06T03:33:00+01:00')

    def test_default_timestamp_has_offset(self):
        status = build_data_status(1)

        self.assertRegex(
            status['generatedAt'],
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$',
        )

    def test_includes_run_started_at_when_given(self):
        generated_at = datetime(2026, 11, 6, 3, 41, 12, tzinfo=timezone.utc)
        run_started_at = datetime(2026, 11, 6, 3, 33, 0, tzinfo=timezone.utc)

        status = build_data_status(3167, generated_at, run_started_at)

        self.assertEqual(status['runStartedAt'], '2026-11-06T03:33:00+00:00')
        self.assertEqual(status['generatedAt'], '2026-11-06T03:41:12+00:00')

    def test_omits_run_started_at_when_not_given(self):
        status = build_data_status(1)

        self.assertNotIn('runStartedAt', status)


class WriteDataStatusTests(unittest.TestCase):
    def test_writes_json_to_given_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'shared' / 'data-status.json'
            generated_at = datetime(2026, 11, 6, 3, 33, 0, tzinfo=timezone.utc)

            write_data_status(path, 42, generated_at)

            with path.open(encoding='utf-8') as status_file:
                status = json.load(status_file)
            self.assertEqual(status['memberCount'], 42)
            self.assertEqual(status['generatedAt'], '2026-11-06T03:33:00+00:00')

    def test_writes_run_started_at(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'data-status.json'
            generated_at = datetime(2026, 11, 6, 3, 41, 12, tzinfo=timezone.utc)
            run_started_at = datetime(2026, 11, 6, 3, 33, 0, tzinfo=timezone.utc)

            write_data_status(path, 2, generated_at, run_started_at)

            with path.open(encoding='utf-8') as status_file:
                status = json.load(status_file)
            self.assertEqual(status['runStartedAt'], '2026-11-06T03:33:00+00:00')

    @unittest.skipIf(os.name == 'nt', 'POSIX permissions are not available on Windows')
    def test_written_file_is_readable_by_web_server(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'data-status.json'

            write_data_status(path, 1)

            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_replaces_existing_file_without_leaving_temp_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'data-status.json'
            path.write_text('{"memberCount": 1}', encoding='utf-8')

            write_data_status(path, 2)
            write_data_status(path, 3)

            with path.open(encoding='utf-8') as status_file:
                self.assertEqual(json.load(status_file)['memberCount'], 3)
            self.assertEqual(sorted(p.name for p in Path(temp_dir).iterdir()), ['data-status.json'])


if __name__ == '__main__':
    unittest.main()
