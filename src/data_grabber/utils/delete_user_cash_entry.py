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

    # Set the name of the cache and the current key namespace
    cache_name = 'user_details'
    cache_namespace = 'api-v1'

    # Calculate the path to the cache relative to the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = os.path.join(script_dir, '../cache')

    # Open the named cache
    cache = dc.Cache(cache_path)

    # Delete both the namespaced API key and the legacy HTML scraper key
    keys = [
        (cache_name, cache_namespace, uid),
        (cache_name, uid),
    ]
    deleted = []
    for key in keys:
        if key in cache:
            del cache[key]
            deleted.append(key)

    if deleted:
        print(f'uid "{uid}" was deleted from the cache "{cache_name}".')
    else:
        print(f'uid "{uid}" was not found in the cache "{cache_name}".')


if __name__ == '__main__':
    main()
