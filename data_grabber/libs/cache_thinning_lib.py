import random
import diskcache as dc

# Diskcache for persistent LRU-Cache
cache = dc.Cache('cache')


def delete_random_cache_data(cache_name: str, percentage: float) -> None:
    """
    Deletes a random percentage of items from a named cache.

    Args:
        cache_name (str): The name of the cache to delete items from.
        percentage (float): The percentage of items to delete.

    Returns:
        None
    """
    # Collect all keys that belong to the named cache
    named_cache_keys = [key for key in cache.iterkeys() if isinstance(key, tuple) and key[0] == cache_name]

    # Calculate the total number of items in the named cachw
    total_items = len(named_cache_keys)

    if total_items == 0:
        print(f"No items found in named cache '{cache_name}'.")
        return

    # calculate of the items to delete
    num_to_delete = int(percentage * total_items / 100)

    # Randomly select keys to delete
    keys_to_delete = random.sample(named_cache_keys, num_to_delete)

    # delete the keys
    deleted_count = 0
    for key in keys_to_delete:
        try:
            del cache[key]
            deleted_count += 1
        except KeyError:
            print(f"Key {key} not found. Skipping deletion.")

    print(f"{deleted_count} items deleted from named cache '{cache_name}'.")
