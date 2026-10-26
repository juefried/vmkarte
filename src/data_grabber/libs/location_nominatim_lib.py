"""
python location_nominatim_lib.py
"""
import json
import os
import time

import requests
from urllib.parse import quote
from geopy.distance import geodesic
from libs.cache_config_lib import get_negative_ttl_seconds, get_ttl_seconds
from libs.location_mapping_rules_lib import analyze_location_for_country, analyze_location_for_postal_code, prepare_location
from libs.paths_lib import CACHE_DIR, CONFIG_PATH
import diskcache as dc
import re

# Diskcache for persistent LRU-Cache
cache = dc.Cache(str(CACHE_DIR))

# Marks a successful Nominatim request that returned no result
NOMINATIM_NEGATIVE = '__nominatim_negative__'

# Read configuration file
with CONFIG_PATH.open('r', encoding='utf-8') as f:
    config = json.load(f)
EMAIL = config['email']

# Default User-Agent for Nominatim; override per deployment via config or environment
DEFAULT_NOMINATIM_USER_AGENT = 'vmkarte/1.0 (+https://github.com/juefried/vmkarte)'


def _resolve_nominatim_user_agent(config_data):
    """
    Resolves the Nominatim User-Agent from environment, configuration or default.

    Args:
        config_data (dict): The loaded configuration dictionary.

    Returns:
        str: The User-Agent to send to Nominatim.
    """
    config_user_agent = config_data.get('nominatim_user_agent')
    if not isinstance(config_user_agent, str):
        config_user_agent = ''
    return (
        os.environ.get('NOMINATIM_USER_AGENT', '').strip()
        or config_user_agent.strip()
        or DEFAULT_NOMINATIM_USER_AGENT
    )


NOMINATIM_USER_AGENT = _resolve_nominatim_user_agent(config)

# Headers with a descriptive User-Agent as required by the Nominatim usage policy
NOMINATIM_HEADERS = {
    'User-Agent': NOMINATIM_USER_AGENT,
    'Accept': 'application/json',
}

# Timeout for Nominatim requests in seconds
NOMINATIM_TIMEOUT = 30


def _get_nominatim(url):
    """
    Sends a GET request to Nominatim and enforces the 1 request/second policy.

    Args:
        url (str): The Nominatim URL to request.

    Returns:
        requests.Response: The HTTP response.
    """
    try:
        return requests.get(url, headers=NOMINATIM_HEADERS, timeout=NOMINATIM_TIMEOUT)
    finally:
        time.sleep(1)


def query_nominatim(searchstring, country_code, use_cache=True):
    """
    Queries the Nominatim API for location details based on the search string and country code.

    Successful lookups are cached with the configured positive TTL. A successful
    request that returns no result is cached with the configured negative TTL, so
    permanently unresolvable locations are not queried on every run. Exceptions
    (for example HTTP 403, 429 or timeouts) are never cached.

    Args:
        searchstring (str): The location to search for.
        country_code (str): The country code to narrow down the search, can be None.
        use_cache (bool): Read an existing Nominatim cache entry. Fresh results are
            still written to the cache.

    Returns:
        dict or None: The location details if found, otherwise None.
    """
    # Check if searchstring is None
    if searchstring is None:
        return None

    # Remove leading and trailing commas and spaces from searchstring
    searchstring = searchstring.strip(', ')

    # Check if country_code is not None
    if country_code is not None:
        # Check if searchstring matches the pattern '^[a-z]{1,3}-(\d{4,5}.*)$'
        match = re.match(r'^[a-z]{1,3}-(\d{4,5}.*)$', searchstring)
        if match:
            # Extract the matched group from searchstring
            searchstring = match.group(1)

    # Reuse a previously successful or negative lookup unless bypassed
    cache_key = ('nominatim', searchstring, country_code)
    if use_cache:
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            if cached_result == NOMINATIM_NEGATIVE:
                return None
            return cached_result

    try:
        # Construct the URL for the Nominatim API request
        url = f"https://nominatim.openstreetmap.org/search?q={quote(searchstring)}&format=json&addressdetails=1&email={EMAIL}"
        if country_code is not None:
            # Add the country code to the URL
            url += f"&countrycodes={country_code}"

        # Send a GET request to the Nominatim API
        response = _get_nominatim(url)

        # Raise an exception if the response status code is not 200
        response.raise_for_status()
        # Parse the response JSON data
        data = response.json()

        if len(data) == 1:
            # Perform another search excluding the found place ID
            exclude_place_id = data[0]['place_id']
            url_exclude = f"{url}&exclude_place_ids={exclude_place_id}"
            response_exclude = _get_nominatim(url_exclude)

            response_exclude.raise_for_status()
            data_exclude = response_exclude.json()

            # Add the new data to the original data
            data.extend(data_exclude)

        result = None
        if data:
            # Define the types of locations to check
            types_to_check = [
                'postal_code', 'administrative', 'post_box', 'city', 'town',
                'village', 'suburb', 'region', 'hamlet', 'political',
                'protected_area', 'county', 'government', 'residential',
                'ceremonial', 'island', 'station', 'post_office',
                'motorway_junction', 'bus_stop'
            ]
            # Check if any of the entries in the data match the types_to_check
            for entry_type in types_to_check:
                for entry in data:
                    if entry['type'] == entry_type:
                        result = entry
                        break
                if result is not None:
                    break

            # If no match is found, use the first entry in the data
            if result is None:
                result = data[0]

        if result is not None:
            cache.set(cache_key, result, expire=get_ttl_seconds('nominatim'))
        else:
            negative_ttl = get_negative_ttl_seconds('nominatim')
            if negative_ttl > 0:
                cache.set(cache_key, NOMINATIM_NEGATIVE, expire=negative_ttl)

        return result

    except (requests.RequestException, ValueError) as e:
        # Print an error message if an exception occurs while fetching location details
        print(f"An error occurred while fetching location details for \"{searchstring}\", country_code={country_code}: {e}")
    return None



def calculate_radius(boundingbox):
    """
    Calculate the radius of a bounding box.

    Args:
        boundingbox (list): A list of four float values representing the south, north, west, and east coordinates of the bounding box.

    Returns:
        float or str: The calculated radius of the bounding box in meters. Returns 'N/A' if the bounding box is not provided.
    """
    if boundingbox:
        # The bounding box is [south, north, west, east]
        south, north, west, east = map(float, boundingbox)
        center_point = ((south + north) / 2, (west + east) / 2)
        north_west = (north, west)
        #south_east = (south, east)
        radius = geodesic(center_point, north_west).meters
        return round(radius)
    return 'N/A'

def examine_locations(members, refresh_uids=()):
    """
    Examines the locations of the members and updates their information.

    Args:
        members (dict): A dictionary containing the members' information.
        refresh_uids (iterable): UIDs whose Nominatim lookups must bypass the cache.
            Fresh results are still written to the cache.

    Returns:
        list: A list of updated members' information.
    """
    updated_members = []  # Initialize an empty list to store updated members' information
    total_members = len(members)  # Get the total number of members
    if isinstance(refresh_uids, str):
        refresh_uids = [refresh_uids]
    refresh_uids = {str(uid) for uid in (refresh_uids or ())}

    for index, uid in enumerate(members, start=1):
        member = members[uid]  # Get the member's information
        location = member.get('location', "").lower().strip()  # Get the member's location
        use_nominatim_cache = str(uid) not in refresh_uids

        postal_code = None  # Initialize variable to store postal code
        country_code = None  # Initialize variable to store country code

        if location:
            if not use_nominatim_cache:
                print(
                    f"Nominatim cache bypassed for {member.get('name', uid)} ({uid})"
                )

            country_code = analyze_location_for_country(location)  # Analyze location for country code
            postal_code = analyze_location_for_postal_code(location)  # Analyze location for postal code
            new_location = prepare_location(location)  # Prepare location for query
            if country_code is None and new_location != location:
                country_code = analyze_location_for_country(new_location)  # Analyze new location for country code
            location = new_location  # Update location

            nominatim_data = None  # Initialize variable to store Nominatim data

            if country_code is not None:
                nominatim_data = query_nominatim(location, country_code, use_cache=use_nominatim_cache)  # Query Nominatim with country code
            else:
                cc_try_list = None  # Initialize variable to store country code try list
                if postal_code is not None:
                    if len(postal_code) == 5:
                        cc_try_list = ['de', 'fr,fi,it', None]  # Set country code try list for postal code length 5
                    else:
                        cc_try_list = ['at,ch', 'dk,nl', None]  # Set country code try list for postal code length not 5
                else:
                    cc_try_list = ['de,at,ch', None]  # Set country code try list for no postal code

                for cc_try in cc_try_list:
                    nominatim_data = query_nominatim(location, cc_try, use_cache=use_nominatim_cache)  # Query Nominatim with country code try
                    if nominatim_data:
                        break  # Break loop if Nominatim data is found

            if nominatim_data:
                member['lat'] = nominatim_data.get('lat', 'N/A')  # Update member's latitude
                member['lon'] = nominatim_data.get('lon', 'N/A')  # Update member's longitude
                member['radius'] = calculate_radius(nominatim_data.get('boundingbox'))  # Calculate radius
            else:
                continue  # Continue to next member if no Nominatim data is found

            member['postal_code'] = postal_code  # Update member's postal code
            member['country_code'] = country_code  # Update member's country code
            updated_members.append(member)  # Add updated member to list

        print(f"Datensatz {index} / {total_members} verarbeitet")  # Print progress

    return updated_members  # Return list of updated members' information
