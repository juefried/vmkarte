#!/usr/bin/python3

import argparse
import diskcache as dc
import os

def main():
    # Argument parser für die Befehlszeilenparameter
    parser = argparse.ArgumentParser(description='Lösche eine uid aus einem benannten Cache.')
    parser.add_argument('uid', type=str, help='Die uid, die gelöscht werden soll')

    args = parser.parse_args()

    uid = args.uid
    cache_name = 'user_details'  # Fester Name des Caches

    # Berechne den Pfad zum Cache relativ zum Skript
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = os.path.join(script_dir, '../cache')

    # Öffne den benannten Cache
    cache = dc.Cache(cache_path)

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
