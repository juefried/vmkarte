import diskcache as dc

def list_cache_contents(cache_dir):
    try:
        # Öffnen des Disk-Cache
        cache = dc.Cache(cache_dir)

        # Check if the cache is empty
        if len(cache) == 0:
            print(f"No entries found in the cache directory {cache_dir}.")
            return

        # Print the header
        print(f"{'Key':<30} {'Size (Bytes)':<15} {'Last Accessed':<25}")
        print("="*70)

        # Iterate through the cache and print details
        for key in cache.iterkeys():
            item = cache.get(key, read=False)
            size = len(item) if item else 0

            if size > 0:
                print(f"{str(key):<30} {size:<15}, country={key[2]}")
            #if (size == 0):
            #    cache.delete(key)
            #if (key[2] == 'at'):
            #    cache.delete(key)

        # Close the cache
        cache.close()

    except Exception as e:
        print(f"An error occurred: {e}")

# Specify the directory containing the disk cache
cache_directory = 'location_cache'
list_cache_contents(cache_directory)
