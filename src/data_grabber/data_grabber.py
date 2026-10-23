#!/usr/bin/python3

import json
import argparse
from libs.data_scraper_lib import get_member_data
from libs.location_nominatim_lib import examine_locations
from libs.paths_lib import MEMBERS_JSON_PATH, SHARED_DIR, VMFORUM_MEMBERS_JSON_PATH


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

    # Parse the command line arguments
    parser.parse_args()

    # Retrieve member data
    members = get_member_data()
    print(f"Total members parsed: {len(members)}")  # Print the total number of members parsed

    # Write the data to a JSON file / just for debug purposes
    with MEMBERS_JSON_PATH.open('w', encoding='utf-8') as file:
        json.dump(members, file, ensure_ascii=False, indent=4)

    # Examine locations
    members = examine_locations(members)

    # Prepare data for the JSON file
    vmforum_members = prepare_vmforum_members(members)

    # Write the data to the JSON file served by the map
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing map data to {VMFORUM_MEMBERS_JSON_PATH}")
    with VMFORUM_MEMBERS_JSON_PATH.open('w', encoding='utf-8') as vmforumfile:
        json.dump(vmforum_members, vmforumfile, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
