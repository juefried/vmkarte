#!/usr/bin/python3

import argparse
import os
import diskcache as dc


def main():
    """
    Main function to delete a user's details from a named cache.

    This function takes a user's unique identifier (uid) as a command line argument and deletes the corresponding
    entry from a named cache.
    """

    # Create an argument parser for command line parameters
    parser = argparse.ArgumentParser(description='Delete a user\'s details from a named cache.')

    # Add an argument for the uid
    parser.add_argument('uid', type=str, help='The unique identifier of the user whose details should be deleted.')

    # Parse the command line arguments
    args = parser.parse_args()

    # Get the uid from the command line arguments
    uid = args.uid

    # Set the name of the cache
    cache_name = 'user_details'

    # Calculate the path to the cache relative to the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = os.path.join(script_dir, '../cache')

    # Open the named cache
    cache = dc.Cache(cache_path)

    # Key for the uid in the cache
    key = (cache_name, uid)

    # Delete the uid from the cache
    if key in cache:
        del cache[key]
        print(f'uid "{uid}" was deleted from the cache "{cache_name}".')
    else:
        print(f'uid "{uid}" was not found in the cache "{cache_name}".')


if __name__ == '__main__':
    main()
