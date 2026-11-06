#!/usr/bin/python3

import argparse
import csv
import json
import sys
from pathlib import Path

from geopy.distance import geodesic

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from libs.location_mapping_rules_lib import (
    analyze_location_for_country,
    analyze_location_for_postal_code,
    prepare_location,
)
from libs.location_precision_lib import (
    PRECISION_CACHE_VERSION,
    build_precision_queries,
    calculate_radius_from_bbox_center,
    extract_place_name,
    precision_cache_key,
)
from libs.paths_lib import (
    CACHE_DIR,
    LOCATION_DETAILS_JSON_PATH,
    REPO_ROOT,
    VMFORUM_MEMBERS_JSON_PATH,
)

DEFAULT_BASELINE_DIR = REPO_ROOT / 'local' / 'baseline'


def _load_json(path):
    with Path(path).open('r', encoding='utf-8') as file:
        return json.load(file)


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_meters(value):
    if isinstance(value, bool):
        return None
    return _to_float(value)


def _index_by_id(entries):
    indexed = {}
    for entry in entries or []:
        if isinstance(entry, dict) and entry.get('id') is not None:
            indexed[str(entry['id'])] = entry
    return indexed


def _sort_key(uid):
    if uid.isdigit():
        return (0, int(uid), '')
    return (1, 0, uid)


def _coordinate(entry, key):
    return _to_float((entry or {}).get(key))


def _distance_between(old, new):
    old_point = (_coordinate(old, 'lat'), _coordinate(old, 'lon'))
    new_point = (_coordinate(new, 'lat'), _coordinate(new, 'lon'))
    if None in old_point or None in new_point:
        return None
    return geodesic(old_point, new_point).meters


def _build_object_label(detail):
    """
    Builds a readable object label without the misleading municipality field.

    Example: "Ebersberg (town), Landkreis Ebersberg, Bayern" instead of
    "Ebersberg, Baiern (VGem Glonn), Landkreis Ebersberg, ...".
    """
    detail = detail or {}
    address = detail.get('address')
    if not isinstance(address, dict):
        address = {}

    name = str(detail.get('name') or '').strip()
    object_type = str(detail.get('addresstype') or detail.get('type') or '').strip()

    if object_type == 'postcode':
        context_keys = (
            'suburb',
            'borough',
            'city_district',
            'city',
            'state',
            'country',
        )
    else:
        context_keys = ('county', 'state', 'country')

    parts = []
    if name:
        label = f"{name} ({object_type})" if object_type else name
        parts.append(label)

    added_context = False
    for key in context_keys:
        value = str(address.get(key) or '').strip()
        if key == 'country' and added_context:
            continue
        if value and value.casefold() != name.casefold() and value not in parts:
            parts.append(value)
            added_context = True

    if parts:
        return ', '.join(parts)
    return detail.get('display_name') or '-'


def resolve_classic_radius(raw_member, detail, cache_get=None):
    """
    Resolves the classic radius of the object chosen by the precision run.

    Preference order:
    1. radius_classic stored directly in location-details.json
    2. boundingbox stored directly in location-details.json
    3. Selected candidate from the precision cache
    """
    detail = detail or {}

    direct = _to_meters(detail.get('radius_classic'))
    if direct is not None:
        return direct

    bbox_radius = calculate_radius_from_bbox_center(detail.get('boundingbox'))
    if isinstance(bbox_radius, (int, float)):
        return float(bbox_radius)

    if cache_get is None:
        return None

    location = (raw_member or {}).get('location')
    if not isinstance(location, str) or not location.strip():
        return None

    variant = detail.get('query_variant')
    countrycodes = detail.get('countrycodes')
    if not variant:
        return None

    location = location.lower().strip()
    country_code = analyze_location_for_country(location)
    prepared = prepare_location(location)
    if country_code is None and prepared != location:
        country_code = analyze_location_for_country(prepared)
    if not prepared:
        return None

    postal_code = analyze_location_for_postal_code(prepared)
    place_name = extract_place_name(prepared, postal_code, country_code)
    params_by_variant = dict(
        build_precision_queries(prepared, place_name, postal_code)
    )
    params = params_by_variant.get(variant)
    if not params:
        return None

    cache_key = precision_cache_key(
        variant, params, countrycodes, PRECISION_CACHE_VERSION
    )
    data = cache_get(cache_key)
    if not isinstance(data, list):
        return None

    wanted_type = str(detail.get('osm_type'))
    wanted_id = str(detail.get('osm_id'))
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if (
            str(entry.get('osm_type')) == wanted_type
            and str(entry.get('osm_id')) == wanted_id
        ):
            radius = calculate_radius_from_bbox_center(entry.get('boundingbox'))
            if isinstance(radius, (int, float)):
                return float(radius)
    return None


def build_classic_radius_lookup(raw_members, details, cache_get=None):
    """Builds a UID -> classic radius mapping for the new result objects."""
    lookup = {}
    for uid, detail in (details or {}).items():
        radius = resolve_classic_radius(
            (raw_members or {}).get(str(uid)),
            detail,
            cache_get=cache_get,
        )
        if radius is not None:
            lookup[str(uid)] = radius
    return lookup


def _build_change_item(
    uid,
    old,
    new,
    raw_member,
    detail,
    classic_radii,
    radius_basis,
    min_radius_growth_m,
    min_radius_growth_pct,
    status,
):
    detail = detail or {}
    raw_member = raw_member or {}
    old = old or {}
    new = new or {}

    precision_rejected = bool(
        detail.get('strategy') == 'classic_fallback' or detail.get('guard')
    )
    rejected = detail.get('rejected_precision') or {}
    detail_address = detail.get('address')
    if not isinstance(detail_address, dict):
        detail_address = {}

    old_radius = _to_meters(old.get('radius'))
    radius_map = _to_meters(new.get('radius'))
    classic_radius = (classic_radii or {}).get(uid)
    if classic_radius is None:
        classic_radius = _to_meters(detail.get('radius_classic'))
    if classic_radius is None:
        bbox_radius = calculate_radius_from_bbox_center(detail.get('boundingbox'))
        if isinstance(bbox_radius, (int, float)):
            classic_radius = float(bbox_radius)

    if radius_basis == 'map':
        effective_radius = radius_map
        basis = 'map' if radius_map is not None else 'unavailable'
    elif radius_basis == 'derived':
        effective_radius = classic_radius
        basis = 'derived' if classic_radius is not None else 'unavailable'
    else:
        if classic_radius is not None:
            effective_radius = classic_radius
            basis = 'derived'
        elif radius_map is not None:
            effective_radius = radius_map
            basis = 'map'
        else:
            effective_radius = None
            basis = 'unavailable'

    distance = _distance_between(old, new) if old and new else None
    radius_delta = (
        effective_radius - old_radius
        if effective_radius is not None and old_radius is not None
        else None
    )
    radius_map_delta = (
        radius_map - old_radius
        if radius_map is not None and old_radius is not None
        else None
    )
    radius_growth_pct = (
        radius_delta / old_radius * 100
        if radius_delta is not None and old_radius
        else None
    )

    outside_old_radius = (
        distance > old_radius
        if distance is not None and old_radius is not None
        else None
    )
    areas_disjoint = (
        distance > old_radius + effective_radius
        if (
            distance is not None
            and old_radius is not None
            and effective_radius is not None
        )
        else None
    )
    radius_grew = bool(
        radius_delta is not None
        and radius_delta > min_radius_growth_m
        and (radius_growth_pct is None or radius_growth_pct > min_radius_growth_pct)
    )
    radius_shrank = bool(radius_delta is not None and radius_delta < 0)
    radius_not_comparable = old_radius is None or effective_radius is None

    flags = []
    if areas_disjoint:
        flags.append('areas_disjoint')
    if outside_old_radius:
        flags.append('outside_old_radius')
    if radius_grew:
        flags.append('radius_grew')
    if radius_shrank:
        flags.append('radius_shrank')
    if radius_not_comparable:
        flags.append('radius_not_comparable')
    if precision_rejected:
        flags.append('precision_rejected')
    if status == 'added':
        flags.append('added')
    if status == 'removed':
        flags.append('removed')

    return {
        'id': uid,
        'name': new.get('name') or old.get('name') or raw_member.get('name', ''),
        'status': status,
        'location': raw_member.get('location', ''),
        'postal_code': raw_member.get('postal_code', ''),
        'country_code': raw_member.get('country_code', ''),
        'old_lat': old.get('lat'),
        'old_lon': old.get('lon'),
        'old_radius': old.get('radius'),
        'new_lat': new.get('lat'),
        'new_lon': new.get('lon'),
        'new_radius': new.get('radius'),
        'distance_m': round(distance, 1) if distance is not None else None,
        'radius_map_m': radius_map,
        'radius_classic_m': classic_radius,
        'radius_basis': basis,
        'effective_radius_m': effective_radius,
        'radius_delta_m': round(radius_delta, 1) if radius_delta is not None else None,
        'radius_map_delta_m': (
            round(radius_map_delta, 1) if radius_map_delta is not None else None
        ),
        'radius_growth_pct': (
            round(radius_growth_pct, 1) if radius_growth_pct is not None else None
        ),
        'outside_old_radius': outside_old_radius,
        'areas_disjoint': areas_disjoint,
        'radius_grew': radius_grew,
        'radius_shrank': radius_shrank,
        'radius_not_comparable': radius_not_comparable,
        'precision_rejected': precision_rejected,
        'guard_distance_m': detail.get('guard_distance_m'),
        'guard_old_radius_m': detail.get('guard_old_radius_m'),
        'guard_precision_radius_m': detail.get('guard_precision_radius_m'),
        'guard_threshold_m': detail.get('guard_threshold_m'),
        'rejected_query_variant': rejected.get('query_variant'),
        'rejected_type': rejected.get('type'),
        'rejected_addresstype': rejected.get('addresstype'),
        'rejected_display_name': rejected.get('display_name'),
        'rejected_label': _build_object_label(rejected),
        'rejected_osm': (
            f"{rejected.get('osm_type')} {rejected.get('osm_id')}"
            if rejected.get('osm_id') is not None
            else None
        ),
        'flags': flags,
        'new_query_variant': detail.get('query_variant'),
        'new_type': detail.get('type'),
        'new_addresstype': detail.get('addresstype'),
        'new_display_name': detail.get('display_name'),
        'new_label': _build_object_label(detail),
        'new_osm': (
            f"{detail.get('osm_type')} {detail.get('osm_id')}"
            if detail.get('osm_id') is not None
            else None
        ),
        'new_county': detail_address.get('county'),
        'new_state': detail_address.get('state'),
        'new_municipality': detail_address.get('municipality'),
    }


def build_location_changes(
    baseline_entries,
    current_entries,
    raw_members=None,
    details=None,
    min_distance=1.0,
    radius_basis='auto',
    classic_radii=None,
    min_radius_growth_m=0.0,
    min_radius_growth_pct=0.0,
    include_uids=None,
):
    """
    Compares two vmforum_members.json datasets.

    Returns:
        tuple: (summary dict, list of change dicts sorted by suspicion)
    """
    baseline = _index_by_id(baseline_entries)
    current = _index_by_id(current_entries)
    raw_members = raw_members or {}
    details = details or {}
    include_uids = {str(uid) for uid in (include_uids or ())}

    summary = {
        'baseline': len(baseline),
        'current': len(current),
        'added': 0,
        'removed': 0,
        'changed': 0,
        'unchanged': 0,
        'guarded': 0,
        'outside_old_radius': 0,
        'areas_disjoint': 0,
        'radius_grew': 0,
        'radius_shrank': 0,
        'radius_not_comparable': 0,
        'precision_rejected': 0,
    }
    changes = []

    for uid in sorted(set(baseline) | set(current), key=_sort_key):
        old = baseline.get(uid)
        new = current.get(uid)
        detail = details.get(uid) or {}
        raw_member = raw_members.get(uid) or {}

        if old is None:
            status = 'added'
        elif new is None:
            status = 'removed'
        else:
            status = 'changed'

        item = _build_change_item(
            uid,
            old,
            new,
            raw_member,
            detail,
            classic_radii,
            radius_basis,
            min_radius_growth_m,
            min_radius_growth_pct,
            status,
        )

        if status == 'changed':
            moved = (
                item['distance_m'] is not None
                and item['distance_m'] >= min_distance
            )
            effective_radius_changed = (
                item['radius_delta_m'] is not None
                and abs(item['radius_delta_m']) >= min_distance
            )
            if not (moved or effective_radius_changed):
                status = 'unchanged'
                item['status'] = status

        if item['precision_rejected'] and status in ('changed', 'unchanged'):
            status = 'guarded'
            item['status'] = status

        summary[status] += 1
        if status == 'unchanged' and uid not in include_uids:
            continue

        if item['precision_rejected']:
            summary['precision_rejected'] += 1

        if status == 'changed':
            if item['outside_old_radius']:
                summary['outside_old_radius'] += 1
            if item['areas_disjoint']:
                summary['areas_disjoint'] += 1
            if item['radius_grew']:
                summary['radius_grew'] += 1
            if item['radius_shrank']:
                summary['radius_shrank'] += 1
            if item['radius_not_comparable']:
                summary['radius_not_comparable'] += 1

        changes.append(item)

    changes.sort(key=_change_sort_key)
    return summary, changes


def _suspicion_rank(item):
    if item.get('areas_disjoint'):
        return 0
    if item.get('outside_old_radius'):
        return 1
    if item.get('radius_grew'):
        return 2
    if item.get('precision_rejected'):
        return 3
    if item.get('status') in ('added', 'removed'):
        return 5
    return 4


def _change_sort_key(item):
    distance = item['distance_m'] if item['distance_m'] is not None else -1.0
    radius_delta = (
        abs(item['radius_delta_m']) if item['radius_delta_m'] is not None else -1.0
    )
    return (
        _suspicion_rank(item),
        -distance,
        -radius_delta,
        _sort_key(item['id']),
    )


def filter_changes(changes, focus):
    if focus == 'all':
        return changes
    if focus == 'outside-old-radius':
        return [
            item for item in changes
            if item['areas_disjoint'] or item['outside_old_radius']
        ]
    if focus == 'radius-grew':
        return [item for item in changes if item['radius_grew']]
    if focus == 'rejected':
        return [item for item in changes if item['precision_rejected']]
    if focus in ('radius-shrank', 'improvements'):
        return [
            item for item in changes
            if item['radius_shrank']
            and not item['areas_disjoint']
            and not item['outside_old_radius']
        ]
    return [
        item for item in changes
        if item['areas_disjoint'] or item['outside_old_radius'] or item['radius_grew']
    ]


def resolve_user_tokens(tokens, raw_members, baseline_entries, current_entries):
    """Resolves UID or exact member name tokens to UIDs."""
    tokens = [token.strip() for token in tokens or [] if token and token.strip()]
    if not tokens:
        return []

    names = {}
    known_uids = set()

    for uid, member in (raw_members or {}).items():
        uid = str(uid)
        known_uids.add(uid)
        name = str((member or {}).get('name', '')).strip()
        if name:
            names.setdefault(name.casefold(), set()).add(uid)

    for entries in (baseline_entries, current_entries):
        for entry in entries or []:
            uid = str(entry.get('id'))
            known_uids.add(uid)
            name = str(entry.get('name', '')).strip()
            if name:
                names.setdefault(name.casefold(), set()).add(uid)

    resolved = []
    unresolved = []
    ambiguous = {}

    for token in tokens:
        if token.isdigit() and token in known_uids:
            resolved.append(token)
            continue

        matches = sorted(names.get(token.casefold(), ()), key=_sort_key)
        if len(matches) == 1:
            resolved.append(matches[0])
        elif len(matches) > 1:
            ambiguous[token] = matches
        else:
            unresolved.append(token)

    if unresolved or ambiguous:
        messages = []
        if unresolved:
            messages.append('Nicht gefunden: ' + ', '.join(unresolved))
        for token, matches in ambiguous.items():
            messages.append(f"Mehrdeutig: '{token}' -> {', '.join(matches)}")
        raise SystemExit('; '.join(messages))

    return list(dict.fromkeys(resolved))


def _print_user_detail(item):
    print(f"\n=== {item['name']} (UID {item['id']}) ===")
    print(f"Ort: {item['location'] or '-'}")
    print(f"Status: {item['status']}")
    print(
        f"Alt: {item['old_lat']}, {item['old_lon']} | "
        f"Radius {item['old_radius']}"
    )
    print(
        f"Neu: {item['new_lat']}, {item['new_lon']} | "
        f"Karte {item['new_radius']} | effektiv {item['effective_radius_m']} "
        f"({item['radius_basis']})"
    )
    print(
        f"Distanz: {item['distance_m']} m | "
        f"Radius-Delta: {item['radius_delta_m']} m "
        f"({item['radius_growth_pct']} %)"
    )
    print(f"Signale: {', '.join(item['flags']) or '-'}")
    print(f"Neu gewählt: {item['new_label']}")
    print(
        f"OSM: {item['new_osm'] or '-'} | "
        f"Variante: {item['new_query_variant'] or '-'}"
    )
    print(f"Nominatim-Adresse: {item['new_display_name'] or '-'}")
    if item['new_municipality']:
        print(
            f"Adressfelder: municipality={item['new_municipality'] or '-'} | "
            f"county={item['new_county'] or '-'} | "
            f"state={item['new_state'] or '-'}"
        )
    if item['precision_rejected']:
        print(
            f"Precision verworfen: Abstand {item['guard_distance_m']} m > "
            f"Schwelle {item['guard_threshold_m']} m "
            f"(alt {item['guard_old_radius_m']} m, "
            f"precision {item['guard_precision_radius_m']} m)"
        )
        print(f"Verworfen: {item['rejected_label']}")
        print(f"Verworfene Nominatim-Adresse: {item['rejected_display_name'] or '-'}")


def _write_json(path, summary, changes):
    with Path(path).open('w', encoding='utf-8') as file:
        json.dump(
            {'summary': summary, 'changes': changes},
            file,
            ensure_ascii=False,
            indent=2,
        )


CSV_FIELDNAMES = [
    'id', 'name', 'status', 'location', 'postal_code', 'country_code',
    'old_lat', 'old_lon', 'old_radius', 'new_lat', 'new_lon', 'new_radius',
    'distance_m', 'radius_map_m', 'radius_classic_m', 'radius_basis',
    'effective_radius_m', 'radius_delta_m', 'radius_map_delta_m',
    'radius_growth_pct', 'outside_old_radius', 'areas_disjoint',
    'radius_grew', 'radius_shrank', 'radius_not_comparable',
    'precision_rejected', 'guard_distance_m', 'guard_old_radius_m',
    'guard_precision_radius_m', 'guard_threshold_m',
    'rejected_query_variant', 'rejected_type', 'rejected_addresstype',
    'rejected_display_name', 'rejected_label', 'rejected_osm', 'flags',
    'new_query_variant', 'new_type', 'new_addresstype', 'new_display_name',
    'new_label', 'new_osm', 'new_county', 'new_state', 'new_municipality',
]


def _write_csv(path, changes):
    with Path(path).open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for item in changes:
            row = dict(item)
            row['flags'] = ','.join(item.get('flags') or [])
            writer.writerow(row)


def _write_markdown(path, summary, changes):
    lines = [
        '# Standort-Vergleich',
        '',
        f"- Baseline: {summary['baseline']}",
        f"- Aktuell: {summary['current']}",
        f"- Geändert: {summary['changed']}",
        f"- Hinzugefügt: {summary['added']}",
        f"- Entfernt: {summary['removed']}",
        f"- Unverändert: {summary['unchanged']}",
        f"- Außerhalb des alten Radius: {summary['outside_old_radius']}",
        f"- Kreise getrennt: {summary['areas_disjoint']}",
        f"- Radius größer: {summary['radius_grew']}",
        f"- Radius kleiner: {summary['radius_shrank']}",
        f"- Radius nicht vergleichbar: {summary['radius_not_comparable']}",
        f"- Precision verworfen: {summary['precision_rejected']}",
        '',
        '| ID | Name | Ort | Distanz (m) | R alt | R neu (eff.) | Basis | Signale | Typ neu |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for item in changes:
        lines.append(
            f"| {item['id']} | {item['name']} | {item['location']} | "
            f"{item['distance_m'] if item['distance_m'] is not None else ''} | "
            f"{item['old_radius'] if item['old_radius'] is not None else ''} | "
            f"{item['effective_radius_m'] if item['effective_radius_m'] is not None else ''} | "
            f"{item['radius_basis']} | {', '.join(item['flags'])} | "
            f"{item['new_addresstype'] or item['new_type'] or ''} |"
        )
    Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _format_row(item):
    distance = f"{item['distance_m']:.0f}" if item['distance_m'] is not None else '-'
    old_radius = item['old_radius'] if item['old_radius'] is not None else '-'
    effective = (
        item['effective_radius_m'] if item['effective_radius_m'] is not None else '-'
    )
    flags = ', '.join(item['flags']) or '-'
    return (
        f"{item['id']:>6}  {distance:>9}  {str(old_radius):>9}  "
        f"{str(effective):>9}  {item['radius_basis']:<11}  "
        f"{flags[:32]:<32}  {str(item['location'])[:28]:<28}  {item['name']}"
    )


def _print_header():
    print(
        f"{'ID':>6}  {'Distanz':>9}  {'R alt':>9}  {'R neu eff':>9}  "
        f"{'Basis':<11}  {'Signale':<32}  {'Ort':<28}  Name"
    )


def _print_rows(rows, limit, title=None):
    if title:
        print(f"\n{title} ({len(rows)}):")
    if not rows:
        print('  keine')
        return

    _print_header()
    shown = rows[:limit]
    for item in shown:
        print(_format_row(item))
    if len(rows) > len(shown):
        print(f"... {len(rows) - len(shown)} weitere")


def _print_summary(summary):
    print(
        f"Baseline: {summary['baseline']} | Aktuell: {summary['current']} | "
        f"geändert: {summary['changed']} | hinzugefügt: {summary['added']} | "
        f"entfernt: {summary['removed']} | unverändert: {summary['unchanged']}"
    )
    print(
        f"Außerhalb des alten Radius: {summary['outside_old_radius']} | "
        f"Kreise getrennt: {summary['areas_disjoint']} | "
        f"Radius größer: {summary['radius_grew']} | "
        f"Radius kleiner: {summary['radius_shrank']} | "
        f"nicht vergleichbar: {summary['radius_not_comparable']} | "
        f"Precision verworfen: {summary['precision_rejected']}"
    )


def _print_report(summary, changes, limit, focus):
    _print_summary(summary)
    focused = filter_changes(changes, focus)

    if focus == 'suspicious':
        outside = [
            item for item in focused
            if item['areas_disjoint'] or item['outside_old_radius']
        ]
        grew = [
            item for item in focused
            if item['radius_grew']
            and not (item['areas_disjoint'] or item['outside_old_radius'])
        ]
        _print_rows(
            outside,
            limit,
            title='Neue Position außerhalb des alten Radius',
        )
        if grew:
            _print_rows(
                grew,
                limit,
                title='Radius größer als zuvor',
            )
        return

    if not focused:
        print('\nKeine passenden Änderungen.')
        return

    if focus in ('radius-shrank', 'improvements'):
        title = 'Verbesserungen: Radius kleiner als zuvor'
    elif focus == 'rejected':
        title = 'Precision verworfen (Classic beibehalten)'
    else:
        title = 'Änderungen'
    _print_rows(focused, limit, title=title)


def _open_cache():
    import diskcache as dc

    return dc.Cache(str(CACHE_DIR))


def main():
    parser = argparse.ArgumentParser(
        description='Compare the frozen location baseline with the current map data.'
    )
    parser.add_argument(
        '--baseline-dir',
        default=str(DEFAULT_BASELINE_DIR),
        help=f'Baseline directory (default: {DEFAULT_BASELINE_DIR})',
    )
    parser.add_argument(
        '--current',
        default=str(VMFORUM_MEMBERS_JSON_PATH),
        help=f'Current vmforum_members.json (default: {VMFORUM_MEMBERS_JSON_PATH})',
    )
    parser.add_argument(
        '--details',
        default=str(LOCATION_DETAILS_JSON_PATH),
        help=f'Precision details from the current run (default: {LOCATION_DETAILS_JSON_PATH})',
    )
    parser.add_argument(
        '--min-distance',
        type=float,
        default=1.0,
        help='Minimum coordinate movement or radius change in meters (default: 1)',
    )
    parser.add_argument(
        '--min-radius-growth-m',
        type=float,
        default=0.0,
        help='Minimum radius growth in meters to flag an entry (default: 0)',
    )
    parser.add_argument(
        '--min-radius-growth-pct',
        type=float,
        default=0.0,
        help='Minimum radius growth in percent to flag an entry (default: 0)',
    )
    parser.add_argument(
        '--radius-basis',
        choices=('auto', 'map', 'derived'),
        default='auto',
        help='Radius used for comparison: derived classic radius, map radius, '
             'or auto (derived when available; default: auto)',
    )
    parser.add_argument(
        '--focus',
        choices=(
            'suspicious',
            'all',
            'outside-old-radius',
            'radius-grew',
            'radius-shrank',
            'improvements',
            'rejected',
        ),
        default='suspicious',
        help='Rows shown on the console (default: suspicious). '
             'radius-shrank and improvements are aliases.',
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Shortcut for --focus all',
    )
    parser.add_argument(
        '--user',
        action='append',
        default=[],
        metavar='UID|NAME',
        help='Show a detailed report for a UID or exact member name; '
             'repeatable or comma-separated',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=30,
        help='Number of rows printed per console section (default: 30)',
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Optional report path (.csv, .json or .md); contains all changes',
    )
    args = parser.parse_args()
    focus = 'all' if args.all else args.focus

    baseline_dir = Path(args.baseline_dir)
    baseline_members_path = baseline_dir / 'members.json'
    baseline_map_path = baseline_dir / 'vmforum_members.json'
    for path in (baseline_members_path, baseline_map_path):
        if not path.is_file():
            raise SystemExit(
                f"Missing baseline file: {path}\n"
                'Run utils/freeze_location_baseline.py first.'
            )

    raw_members = _load_json(baseline_members_path)
    baseline_entries = _load_json(baseline_map_path)
    current_entries = _load_json(args.current)

    user_tokens = []
    for value in args.user or []:
        for token in value.split(','):
            if token.strip():
                user_tokens.append(token.strip())

    selected_uids = resolve_user_tokens(
        user_tokens, raw_members, baseline_entries, current_entries
    ) if user_tokens else []
    selected_uid_set = set(selected_uids)

    details = {}
    details_path = Path(args.details)
    if details_path.is_file():
        details = _load_json(details_path)

    classic_radii = {}
    cache = None
    if args.radius_basis in ('auto', 'derived') and details:
        try:
            cache = _open_cache()
            classic_radii = build_classic_radius_lookup(
                raw_members, details, cache_get=cache.get
            )
        except Exception as error:
            print(f"Warning: could not derive classic radii from cache: {error}")
        finally:
            if cache is not None:
                cache.close()

    summary, changes = build_location_changes(
        baseline_entries,
        current_entries,
        raw_members=raw_members,
        details=details,
        min_distance=args.min_distance,
        radius_basis=args.radius_basis,
        classic_radii=classic_radii,
        min_radius_growth_m=args.min_radius_growth_m,
        min_radius_growth_pct=args.min_radius_growth_pct,
        include_uids=selected_uid_set,
    )

    if selected_uid_set:
        selected_changes = [
            item for item in changes if item['id'] in selected_uid_set
        ]
        found_ids = {item['id'] for item in selected_changes}
        for item in selected_changes:
            _print_user_detail(item)
        for uid in selected_uids:
            if uid not in found_ids:
                raw_member = raw_members.get(uid) or {}
                print(
                    f"\n=== {raw_member.get('name', '?')} (UID {uid}) ===\n"
                    'Kein aufgelöster Standort in Baseline/Karte.'
                )
        output_changes = selected_changes
    else:
        _print_report(summary, changes, args.limit, focus)
        output_changes = changes

    if args.output:
        output_path = Path(args.output)
        suffix = output_path.suffix.lower()
        if suffix == '.json':
            _write_json(output_path, summary, output_changes)
        elif suffix in ('.md', '.markdown'):
            _write_markdown(output_path, summary, output_changes)
        else:
            _write_csv(output_path, output_changes)
        print(f"\nReport written to {output_path}")


if __name__ == '__main__':
    main()
