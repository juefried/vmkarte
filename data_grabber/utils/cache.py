import diskcache as dc
import random
import os

def list_cache_contents(cache, cache_names=None):
    try:
        # Überprüfen, ob der Cache leer ist
        if len(cache) == 0:
            print(f"No entries found in the cache directory {cache_dir}.")
            return

        # Print the header
        print(f"{'Key':<30} {'Size (Bytes)':<15}")
        print("="*45)

        # Funktion zur Größenberechnung
        def get_item_size(item):
            return len(item) if item else 0

        # Alle Schlüssel im Cache durchsuchen
        for key in cache.iterkeys():
            # Wenn ein Array von Cache-Namen übergeben wurde, nur die relevanten Schlüssel anzeigen
            if cache_names and (not isinstance(key, tuple) or key[0] not in cache_names):
                continue

            item = cache.get(key, read=False)
            size = get_item_size(item)

            if size > 0:
                if isinstance(key, tuple) and len(key) > 2:
                    print(f"{str(key):<30} {size:<15}, country={key[2]}")
                else:
                    print(f"{str(key):<30} {size:<15}")

    except Exception as e:
        print(f"An error occurred: {e}")

def delete_random_data(cache, cache_name, percentage):
    named_cache_keys = [key for key in cache.iterkeys() if isinstance(key, tuple) and key[0] == cache_name]

    total_items = len(named_cache_keys)

    if total_items == 0:
        print(f"No items found in named cache '{cache_name}'.")
        return

    # 1% der Einträge berechnen
    num_to_delete = int(percentage * total_items / 100)

    # Zufällige Schlüssel auswählen
    keys_to_delete = random.sample(named_cache_keys, num_to_delete)

    # Schlüssel löschen
    for key in keys_to_delete:
        del cache[key]

    print(f"{num_to_delete} items deleted from named cache '{cache_name}'.")


def print_cache_names(cache):
    cache_keys = cache.iterkeys()

    # Dictionary to store the size and count of items in named caches
    named_caches = {}

    for key in cache_keys:
        # Keys can be tuples where the first part is the name of the named cache
        if isinstance(key, tuple) and len(key) > 1:
            cache_name = key[0]
            item = cache.get(key, read=False)
            size = len(item) if item else 0
            if cache_name in named_caches:
                named_caches[cache_name]['size'] += size
                named_caches[cache_name]['count'] += 1
            else:
                named_caches[cache_name] = {'size': size, 'count': 1}

    if not named_caches:
        print("No named caches found.")
    else:
        print(f"{'Named Cache':<30} {'Size (Bytes)':<15} {'Item Count':<15}")
        print("="*60)
        for name, info in named_caches.items():
            print(f"{name:<30} {info['size']:<15} {info['count']:<15}")
        print()

def delete_named_cache(cache, cache_name):
    named_cache_keys = [key for key in cache.iterkeys() if isinstance(key, tuple) and key[0] == cache_name]

    total_items = len(named_cache_keys)

    if total_items == 0:
        print(f"No items found in named cache '{cache_name}'.")
        return

    print(f"Found {total_items} items in named cache '{cache_name}'.")

    # Delete all keys
    for key in named_cache_keys:
        try:
            print(f"Deleting key: {key}")
            del cache[key]
        except KeyError:
            print(f"Key not found: {key}")
        except Exception as e:
            print(f"Error deleting key {key}: {e}")

    print(f"All items deleted from named cache '{cache_name}'.")

# Berechne den Pfad zum Cache relativ zum Skript
script_dir = os.path.dirname(os.path.abspath(__file__))
cache_path = os.path.join(script_dir, '../cache')

# Öffne den benannten Cache
cache = dc.Cache(cache_path)


#del cache[('nominatim', 'warwickshire.   uk', 'gb', None)]
print_cache_names(cache)
#delete_named_cache(cache, "user_details")
#delete_random_data(cache, "member_page", 1)
#delete_random_data(cache, "user_details", 1)
#delete_random_data(cache, "nominatim", 1)
#delete_random_data(cache, "members_dict", 100)
list_cache_contents(cache, 'nominatim')

cache.close()