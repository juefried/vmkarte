#!/usr/bin/python3

import argparse
import json

from libs.data_scraper_lib import get_member_data
from libs.location_nominatim_lib import examine_locations
from libs.paths_lib import APP_DIR, MEMBERS_JSON_PATH, REPO_ROOT, SHARED_DIR, VMFORUM_MEMBERS_JSON_PATH


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

    # Parse the command line arguments
    args = parser.parse_args()
    refresh_user_tokens = parse_refresh_user_tokens(args.refresh_user)

    # Raw member data must never be exposed through the web server. Remove
    # stale copies before the long scrape starts.
    remove_stale_members_json(include_current=not args.debug)

    # Retrieve member data
    members, refresh_uids = get_member_data(
        refresh_members=args.refresh_members,
        refresh_user_tokens=refresh_user_tokens,
    )
    print(f"Total members parsed: {len(members)}")  # Print the total number of members parsed

    if args.debug:
        with MEMBERS_JSON_PATH.open('w', encoding='utf-8') as file:
            json.dump(members, file, ensure_ascii=False, indent=4)
        print(f"Debug member data written to {MEMBERS_JSON_PATH}")

    # Examine locations
    members = examine_locations(members, refresh_uids=refresh_uids)

    # Prepare data for the JSON file
    vmforum_members = prepare_vmforum_members(members)

    # Write the data to the JSON file served by the map
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing map data to {VMFORUM_MEMBERS_JSON_PATH}")
    with VMFORUM_MEMBERS_JSON_PATH.open('w', encoding='utf-8') as vmforumfile:
        json.dump(vmforum_members, vmforumfile, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
