#!/usr/bin/python3

import argparse
import json
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from libs.paths_lib import (
    MEMBERS_JSON_PATH,
    REPO_ROOT,
    VMFORUM_MEMBERS_JSON_PATH,
)

DEFAULT_BASELINE_DIR = REPO_ROOT / 'local' / 'baseline'


def _load_json(path):
    with Path(path).open('r', encoding='utf-8') as file:
        return json.load(file)


def main():
    """
    Freezes the current debug members.json and map JSON as a comparison baseline.

    Both files are copied with their original names into local/baseline. The
    baseline is intentionally not overwritten unless --force is given.
    """
    parser = argparse.ArgumentParser(
        description='Freeze members.json and vmforum_members.json as a local baseline.'
    )
    parser.add_argument(
        '--baseline-dir',
        default=str(DEFAULT_BASELINE_DIR),
        help=f'Target directory (default: {DEFAULT_BASELINE_DIR})',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite an existing baseline',
    )
    args = parser.parse_args()

    sources = {
        'members.json': MEMBERS_JSON_PATH,
        'vmforum_members.json': VMFORUM_MEMBERS_JSON_PATH,
    }
    missing = [str(path) for path in sources.values() if not path.is_file()]
    if missing:
        raise SystemExit(
            'Missing baseline source(s): ' + ', '.join(missing) + '\n'
            'Run the grabber once with --debug before freezing the baseline.'
        )

    baseline_dir = Path(args.baseline_dir)
    baseline_dir.mkdir(parents=True, exist_ok=True)

    targets = {
        'members.json': baseline_dir / 'members.json',
        'vmforum_members.json': baseline_dir / 'vmforum_members.json',
    }
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing and not args.force:
        raise SystemExit(
            'Baseline already exists: ' + ', '.join(existing) + '\n'
            'Use --force to replace it.'
        )

    for name, source in sources.items():
        target = targets[name]
        shutil.copy2(source, target)
        print(f"Froze {source} -> {target}")

    members = _load_json(targets['members.json'])
    map_entries = _load_json(targets['vmforum_members.json'])
    if not isinstance(members, dict) or not isinstance(map_entries, list):
        raise SystemExit('Baseline copy has an unexpected JSON shape.')

    print(
        f"Baseline contains {len(members)} raw members and "
        f"{len(map_entries)} map entries."
    )


if __name__ == '__main__':
    main()
