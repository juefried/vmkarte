import random
import diskcache as dc

# Diskcache for persistent LRU-Cache
cache = dc.Cache('cache')

def delete_random_cache_data(cache_name, percentage):
    named_cache_keys = [key for key in cache.iterkeys() if isinstance(key, tuple) and key[0] == cache_name]

    total_items = len(named_cache_keys)

    if total_items == 0:
        print(f"No items found in named cache '{cache_name}'.")
        return

    num_to_delete = int(percentage * total_items / 100)

    # Zufällige Schlüssel auswählen
    keys_to_delete = random.sample(named_cache_keys, num_to_delete)

    # Schlüssel löschen
    for key in keys_to_delete:
        del cache[key]

    print(f"{num_to_delete} items deleted from named cache '{cache_name}'.")