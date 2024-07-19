#!/usr/bin/python3

import argparse
import diskcache as dc

def main():
    # Argument parser für die Befehlszeilenparameter
    parser = argparse.ArgumentParser(description='Lösche eine uid aus einem benannten Cache.')
    parser.add_argument('uid', type=str, help='Die uid, die gelöscht werden soll')

    args = parser.parse_args()

    uid = args.uid
    cache_name = 'my_named_cache'  # Fester Name des Caches

    # Öffne den benannten Cache
    cache = dc.Cache('../cache')

    # Schlüssel für die uid im Cache
    key = ('user_details', uid)

    # Lösche die uid aus dem Cache
    if key in cache:
        del cache[key]
        print(f'uid "{uid}" wurde aus dem Cache "{cache_name}" gelöscht.')
    else:
        print(f'uid "{uid}" nicht im Cache "{cache_name}" gefunden.')

if __name__ == '__main__':
    main()
