#!/usr/bin/python3

import argparse
import json
from datetime import datetime
from pathlib import Path

from libs.data_status_lib import write_data_status
from libs.forum_api_lib import get_member_data
from libs.json_io_lib import write_json_atomic
from libs.location_nominatim_lib import (
    LOCATION_STRATEGIES,
    PRECISION_GUARDS,
    examine_locations,
)
from libs.paths_lib import (
    APP_DIR,
    DATA_STATUS_JSON_PATH,
    LOCATION_DETAILS_JSON_PATH,
    MEMBERS_JSON_PATH,
    REPO_ROOT,
    SHARED_DIR,
    VMFORUM_MEMBERS_JSON_PATH,
)


def remove_stale_members_json(include_current=True):
    """
    Removes raw member data that must never be served by the web server.

    The current debug file is only removed when include_current is true. Legacy
    copies in the shared/web directory, in the old local shared directory and in
    the repository root are always removed.
    """
    paths = [
        SHARED_DIR / 'members.json',
        APP_DIR / 'shared' / 'members.json',
        REPO_ROOT / 'members.json',
    ]
    if include_current:
        paths.append(MEMBERS_JSON_PATH)

    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            print(f"Could not remove {path}: {error}")


def prepare_vmforum_members(members):
    """
    Reduces member dictionaries to the fields used by the map.
    """
    vmforum_members = []
    for member in members:
        data = {
            'id': member['uid'],
            'name': member['name'],
            'lat': member['lat'],
            'lon': member['lon'],
            'radius': member['radius']
        }
        if member.get('profile_updated_at'):
            data['profile_updated_at'] = member['profile_updated_at']

        for key in ['vm', 'tr', 'lr', 'other']:
            if member.get(key):
                data[key] = member[key]

        vmforum_members.append(data)

    return vmforum_members


def remove_internal_fields(members):
    """
    Removes internal API bookkeeping fields before writing debug data.
    """
    return {
        uid: {
            key: value
            for key, value in member.items()
            if not key.startswith('_')
        }
        for uid, member in members.items()
    }


def parse_refresh_user_tokens(values):
    """
    Flattens repeated and comma-separated --refresh-user values.

    Args:
        values (list): Raw argparse values.

    Returns:
        list: Unique, trimmed UID or name tokens in input order.
    """
    tokens = []
    for value in values or []:
        for token in value.split(','):
            token = token.strip()
            if token:
                tokens.append(token)
    return list(dict.fromkeys(tokens))


def load_members_from_file(path):
    """
    Loads a frozen debug members.json snapshot instead of scraping the forum.

    The snapshot is the same mapping (uid -> member) that --debug writes before
    locations are examined. It therefore contains the raw address strings but no
    coordinates.
    """
    source = Path(path)
    if not source.is_file():
        raise SystemExit(f"Members snapshot not found: {source}")

    try:
        with source.open('r', encoding='utf-8') as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not read members snapshot {source}: {error}") from error

    if not isinstance(data, dict):
        raise SystemExit(
            f"Members snapshot {source} must contain a JSON object keyed by UID."
        )

    return data


def main():
    """
    Main function to run the data grabber.

    This function parses command line arguments, retrieves member data,
    examines locations, and writes the results to a JSON file.

    Args:
        None

    Returns:
        None
    """

    # Create an argument parser
    parser = argparse.ArgumentParser()

    # Deprecated: accepted for compatibility with existing cron and IDE configurations
    parser.add_argument(
        '--fast',
        action='store_true',
        help='Deprecated, has no effect'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Write raw member data to members.json (private, not web-served)'
    )
    parser.add_argument(
        '--refresh-members',
        action='store_true',
        help='Ignore the 23h members list cache and reload all member pages'
    )
    parser.add_argument(
        '--refresh-user',
        action='append',
        default=[],
        metavar='UID|NAME',
        help='Refresh profile and Nominatim data for a UID or exact forum name; '
             'repeatable or comma-separated'
    )
    parser.add_argument(
        '--location-strategy',
        choices=LOCATION_STRATEGIES,
        default='precision',
        help="Location resolution strategy (default: precision). 'precision' uses "
             "structured queries, PLZ-aware area selection and a versioned Nominatim cache. "
             "'classic' keeps the historical behavior."
    )
    parser.add_argument(
        '--precision-guard',
        choices=PRECISION_GUARDS,
        default='disjoint',
        help="Guard for the precision strategy (default: disjoint). "
             "'disjoint' keeps the classic result only when the precision and "
             "classic areas do not overlap. 'old-radius' is stricter."
    )
    parser.add_argument(
        '--refresh-locations',
        action='store_true',
        help='Ignore the Nominatim cache for every member (useful during local testing)'
    )
    parser.add_argument(
        '--write-location-details',
        action='store_true',
        help='Write location-details.json for local comparison (contains personal data)'
    )
    parser.add_argument(
        '--members-from',
        metavar='PATH',
        default=None,
        help='Load raw members from a frozen debug members.json instead of the forum API'
    )

    # Parse the command line arguments
    args = parser.parse_args()
    refresh_user_tokens = parse_refresh_user_tokens(args.refresh_user)
    run_started_at = datetime.now().astimezone()

    if args.members_from and (refresh_user_tokens or args.refresh_members):
        raise SystemExit(
            '--members-from cannot be combined with --refresh-members or --refresh-user.'
        )

    if args.members_from:
        members = load_members_from_file(args.members_from)
        refresh_uids = set()
        print(f"Loaded {len(members)} members from {args.members_from}")
    else:
        members = None
        refresh_uids = set()

    # Raw member data must never be exposed through the web server. Remove
    # stale copies before the long scrape starts.
    remove_stale_members_json(include_current=not args.debug)

    if members is None:
        members, refresh_uids = get_member_data(
            refresh_members=args.refresh_members,
            refresh_user_tokens=refresh_user_tokens,
        )
        print(f"Total members parsed: {len(members)}")  # Print the total number of members parsed

    if args.debug:
        write_json_atomic(MEMBERS_JSON_PATH, remove_internal_fields(members), indent=4)
        print(f"Debug member data written to {MEMBERS_JSON_PATH}")

    # Examine locations
    updated_members = examine_locations(
        members,
        refresh_uids=refresh_uids,
        strategy=args.location_strategy,
        refresh_locations=args.refresh_locations,
        precision_guard=args.precision_guard,
    )

    if args.location_strategy == 'precision' and args.write_location_details:
        location_details = {
            str(uid): member['_location_match']
            for uid, member in members.items()
            if member.get('_location_match')
        }
        if location_details:
            write_json_atomic(LOCATION_DETAILS_JSON_PATH, location_details)
            print(f"Location details written to {LOCATION_DETAILS_JSON_PATH}")

    # Prepare data for the JSON file
    vmforum_members = prepare_vmforum_members(updated_members)

    # Write the data to the JSON file served by the map
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing map data to {VMFORUM_MEMBERS_JSON_PATH}")
    write_json_atomic(VMFORUM_MEMBERS_JSON_PATH, vmforum_members)

    # Metadata is written after the map data succeeded. A failure here must not
    # abort the grabber run or invalidate the freshly written member data.
    try:
        print(f"Writing data status to {DATA_STATUS_JSON_PATH}")
        write_data_status(
            DATA_STATUS_JSON_PATH,
            len(vmforum_members),
            run_started_at=run_started_at,
        )
    except Exception as error:
        print(f"Warning: Could not write {DATA_STATUS_JSON_PATH}: {error}")


if __name__ == "__main__":
    main()
