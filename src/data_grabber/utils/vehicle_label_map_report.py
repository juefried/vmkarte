import argparse
import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from libs.forum_api_lib import (
    MEMBERS_DICT_CACHE_KEY,
    UNKNOWN_VEHICLE_CACHE_KEY,
    cache,
)
from libs.paths_lib import MEMBERS_JSON_PATH
from libs.vehicle_label_lib import (
    VEHICLE_FIELDS,
    VehicleLabelResolver,
    load_vehicle_label_map,
)

RAW_OPTION_PATTERN = re.compile(r'[a-z0-9_-]+')


def iter_members(value):
    if isinstance(value, dict):
        return value.values()
    if isinstance(value, list):
        return value
    return ()


def collect_report():
    resolver = VehicleLabelResolver(load_vehicle_label_map())
    known_labels = {
        field: set(resolver.mapping[field].values())
        for field in VEHICLE_FIELDS
    }
    entries = {}

    def add(field, raw, source, count=None, last_seen=None):
        key = (field, raw)
        entry = entries.setdefault(
            key,
            {
                'field': field,
                'raw': raw,
                'count': None,
                'last_seen': last_seen,
                'sources': set(),
            },
        )
        entry['sources'].add(source)
        if count is not None:
            entry['count'] = max(entry['count'] or 0, count)
        if last_seen and not entry['last_seen']:
            entry['last_seen'] = last_seen

    def add_member_value(field, value, source):
        if not isinstance(value, str):
            return
        raw = value.strip()
        if not raw or resolver.is_known(field, raw):
            return
        if raw in known_labels[field]:
            return
        if raw != raw.casefold() or ' ' in raw:
            return
        if not RAW_OPTION_PATTERN.fullmatch(raw):
            return
        add(field, raw, source, count=1)

    members = cache.get(MEMBERS_DICT_CACHE_KEY)
    for member in iter_members(members):
        if not isinstance(member, dict):
            continue
        for field in VEHICLE_FIELDS:
            add_member_value(field, member.get(field), 'members_cache')

    if MEMBERS_JSON_PATH.exists():
        try:
            debug_members = json.loads(MEMBERS_JSON_PATH.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            debug_members = None
        for member in iter_members(debug_members):
            if not isinstance(member, dict):
                continue
            for field in VEHICLE_FIELDS:
                add_member_value(field, member.get(field), 'members_json')

    logged = cache.get(UNKNOWN_VEHICLE_CACHE_KEY)
    if isinstance(logged, dict):
        for item in logged.values():
            if not isinstance(item, dict):
                continue
            field = item.get('field')
            raw = item.get('raw')
            if field in VEHICLE_FIELDS and isinstance(raw, str) and raw.strip():
                raw = raw.strip()
                if not resolver.is_known(field, raw):
                    add(field, raw, 'unknown_log', last_seen=item.get('last_seen'))

    result = []
    for entry in entries.values():
        guess, confidence, method = resolver.resolve(entry['field'], entry['raw'])
        result.append(
            {
                'field': entry['field'],
                'raw': entry['raw'],
                'count': entry['count'],
                'last_seen': entry['last_seen'],
                'guess': guess,
                'confidence': confidence,
                'method': method,
                'sources': sorted(entry['sources']),
            }
        )

    result.sort(
        key=lambda item: (
            VEHICLE_FIELDS.index(item['field']),
            item['confidence'],
            item['raw'],
        )
    )
    return {
        'map_sizes': {
            field: len(resolver.mapping[field])
            for field in VEHICLE_FIELDS
        },
        'unknown': result,
    }


def print_text(report):
    print('Vehicle label report')
    print(
        'Map: '
        + ', '.join(
            f"{field}={size}"
            for field, size in report['map_sizes'].items()
        )
    )
    unknown = report['unknown']
    print(f'Unknown values: {len(unknown)}')
    if not unknown:
        return

    current_field = None
    for entry in unknown:
        if entry['field'] != current_field:
            current_field = entry['field']
            print(f'\n{current_field}:')
        details = []
        if entry['count'] is not None:
            details.append(f"{entry['count']} members")
        if entry['last_seen']:
            details.append(f"last seen {entry['last_seen']}")
        if entry['sources']:
            details.append('source: ' + ', '.join(entry['sources']))
        suffix = f" ({'; '.join(details)})" if details else ''
        print(f"  {entry['raw']}{suffix}")
        print(
            f"    guess: {entry['guess']} "
            f"({entry['method']}, confidence {entry['confidence']:.2f})"
        )


def main():
    parser = argparse.ArgumentParser(
        description='Report vehicle option values missing from vehicle_label_map.json.'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Print the report as JSON.',
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit with status 1 if unknown values are found.',
    )
    args = parser.parse_args()

    report = collect_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)

    if args.strict and report['unknown']:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
