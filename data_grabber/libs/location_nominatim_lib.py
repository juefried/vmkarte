"""
python location_nominatim_lib.py
"""
import json
import requests
from urllib.parse import quote
from time import sleep
from geopy.distance import geodesic
from libs.location_mapping_rules_lib import analyze_location_for_country, analyze_location_for_postal_code, prepare_location
import diskcache as dc
import re

# Diskcache for persistent LRU-Cache
cache = dc.Cache('cache')

# Read configuration file
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)
EMAIL = config['email']

# Start a session
session = requests.Session()

# Headers to mimic a browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

@cache.memoize(name='nominatim', expire=60*60*24*365)
def query_nominatim(searchstring, country_code):
    if searchstring is None:
        return None
    searchstring = searchstring.strip(', ')
    try:
        if country_code is not None:
            match = re.match(r'^[a-z]{1,3}-(\d{4,5}.*)$', searchstring)
            if match:
                searchstring = match.group(1)

        url = f"https://nominatim.openstreetmap.org/search?q={quote(searchstring)}&format=json&addressdetails=1&email={EMAIL}"
        if country_code is not None:
            url += f"&countrycodes={country_code}"

        response = requests.get(url)
        sleep(1)  # Be polite and do not overwhelm the API with requests
        response.raise_for_status()
        data = response.json()
        if data:
            types_to_check = [
                'postal_code',
                'administrative',
                'post_box',
                'city',
                'town',
                'village',
                'suburb',
                'region',
                'hamlet',
                'political',
                'protected_area',
                'county',
                'government',
                'residential'
                'ceremonial',
                'island',
                'station',
                'post_office',
                'motorway_junction',
                'bus_stop'
            ]
            for entry_type in types_to_check:
                for entry in data:
                    if entry['type'] == entry_type:
                        return entry

            type = entry['type']
            return data[0]

    except requests.RequestException as e:
        print(f"An error occurred while fetching location details for \"{searchstring}\", country_code={country_code}: {e}")
    return None


def calculate_radius(boundingbox):
    if boundingbox:
        # The bounding box is [south, north, west, east]
        south, north, west, east = map(float, boundingbox)
        center_point = ((south + north) / 2, (west + east) / 2)
        north_west = (north, west)
        #south_east = (south, east)
        radius = geodesic(center_point, north_west).meters
        return round(radius)
    return 'N/A'

def examine_locations(members):
    updated_members = []
    total_members = len(members)

    for index, uid in enumerate(members, start=1):
        member = members[uid]
        location = member.get('location', "").lower().strip()

        postal_code = None
        country_code = None
        if location:
            country_code = analyze_location_for_country(location)
            postal_code = analyze_location_for_postal_code(location)
            new_location = prepare_location(location)
            if country_code is None and new_location != location:
                country_code = analyze_location_for_country(new_location)
            location=new_location

            nominatim_data = None

            if country_code is not None:
                nominatim_data = query_nominatim(location, country_code)
            else:
                cc_try_list = None
                if postal_code is not None:
                    if len(postal_code) == 5:
                        cc_try_list = ['de', 'fr,fi,it', None]
                    else:
                        cc_try_list = ['at,ch', 'dk,nl', None]
                else:
                    cc_try_list = ['de,at,ch', None]

                for cc_try in cc_try_list:
                    nominatim_data = query_nominatim(location, cc_try)
                    if nominatim_data:
                        break

            if nominatim_data:
                member['lat'] = nominatim_data.get('lat', 'N/A')
                member['lon'] = nominatim_data.get('lon', 'N/A')
                member['radius'] = calculate_radius(nominatim_data.get('boundingbox'))
            else: continue

            member['postal_code'] = postal_code
            member['country_code'] = country_code
            updated_members.append(member)

        print(f"Datensatz {index} / {total_members} verarbeitet")

    return updated_members
