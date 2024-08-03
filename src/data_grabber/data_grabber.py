#!/usr/bin/python3

import json
import argparse
from libs.data_scraper_lib import get_member_data
from libs.location_nominatim_lib import examine_locations
from libs.cache_thinning_lib import delete_random_cache_data

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

    # Add an optional argument for using the cache
    parser.add_argument(
        '--fast',
        action='store_true',
        help='Use the cache maximally'
    )

    # Parse the command line arguments
    args = parser.parse_args()

    # Shuffle the cache to achieve a better distribution of access times
    # This can be removed after a few months
    if not args.fast:
        delete_random_cache_data("user_details", 1)
        delete_random_cache_data("nominatim", 1)

    # Retrieve member data
    members = get_member_data()
    print(f"Total members parsed: {len(members)}")  # Print the total number of members parsed

    # Write the data to a JSON file / just for debug purposes
    with open('shared/members.json', 'w', encoding='utf-8') as file:
        json.dump(members, file, ensure_ascii=False, indent=4)
    file.close()

    # Examine locations
    members = examine_locations(members)

    # Prepare data for the JSON file
    vmforum_members = []
    for member in members:

        data = {
            'id': member['uid'],
            'name': member['name'],
            'lat': member['lat'],
            'lon': member['lon'],
            'radius': member['radius']
        }
        for key in ['vm', 'tr', 'lr', 'other']:
            if member.get(key):
                data[key] = member[key]

        vmforum_members.append(data)

    # Write the data to a JSON file
    with open('shared/vmforum_members.json', 'w', encoding='utf-8') as vmforumfile:
        json.dump(vmforum_members, vmforumfile, ensure_ascii=False, indent=2)
    vmforumfile.close()

if __name__ == "__main__":
    main()
