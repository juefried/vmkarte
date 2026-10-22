#!/usr/bin/python3

import argparse
import os
import diskcache as dc


def main():
    """
    Deletes all entries from the named cache 'nominatim'.

    This is useful after changing the Nominatim request logic, because older
    failures may have been cached as None.
    """
    parser = argparse.ArgumentParser(description="Delete all 'nominatim' cache entries.")
    parser.add_argument(
        '--cache',
        default=None,
        help='Path to the diskcache directory (default: ../cache relative to this script).'
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = args.cache or os.path.join(script_dir, '..', 'cache')
    cache_path = os.path.abspath(cache_path)

    cache = dc.Cache(cache_path)
    expired_count = cache.expire()
    keys_to_delete = [
        key for key in cache.iterkeys()
        if isinstance(key, tuple) and key and key[0] == 'nominatim'
    ]

    deleted_count = 0
    for key in keys_to_delete:
        try:
            del cache[key]
            deleted_count += 1
        except KeyError:
            pass

    print(
        f"Removed {expired_count} expired entries and deleted {deleted_count} "
        f"'nominatim' entries from the cache at {cache_path}."
    )
    cache.close()


if __name__ == '__main__':
    main()
