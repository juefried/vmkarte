"""
python location_nominatim_lib.py
"""
import json
import os
import time

import requests
from urllib.parse import quote, urlencode
from geopy.distance import geodesic
from libs.cache_config_lib import get_negative_ttl_seconds, get_ttl_seconds
from libs.location_mapping_rules_lib import (
    analyze_location_for_country,
    analyze_location_for_postal_code,
    country_code_candidates,
    order_country_codes,
    prepare_location,
)
from libs.location_precision_lib import (
    PRECISION_CACHE_VERSION,
    build_precision_queries,
    calculate_radius_from_point,
    candidate_is_good_enough,
    candidate_matches_location,
    candidate_sort_key,
    choose_smaller_area,
    extract_place_name,
    is_postcode,
    postcode_matches,
    precision_cache_key,
    precision_rejection,
    rank_nominatim_candidates,
    summarize_candidate,
)
from libs.paths_lib import CACHE_DIR, CONFIG_PATH
import diskcache as dc
import re

# Diskcache for persistent LRU-Cache
cache = dc.Cache(str(CACHE_DIR))

# Marks a successful Nominatim request that returned no result
NOMINATIM_NEGATIVE = '__nominatim_negative__'

LOCATION_STRATEGIES = ('classic', 'precision')
PRECISION_GUARDS = ('none', 'old-radius', 'disjoint')

# Read configuration file
with CONFIG_PATH.open('r', encoding='utf-8') as f:
    config = json.load(f)
EMAIL = config['email']

# Default User-Agent for Nominatim; override per deployment via config or environment
DEFAULT_NOMINATIM_USER_AGENT = 'vmkarte/2.0 (+https://github.com/juefried/vmkarte)'


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


def query_nominatim(searchstring, country_code, use_cache=True, cache_only=False):
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
        cache_only (bool): Return None instead of performing a network request on
            a cache miss. Used for the precision guard, which must stay offline.

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

    if cache_only:
        return None

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


def _build_nominatim_url(params, countrycodes):
    """Builds a Nominatim search URL from structured parameters."""
    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"{urlencode(params)}&format=json&addressdetails=1&email={quote(EMAIL)}&limit=10"
    )
    if countrycodes:
        url += f"&countrycodes={countrycodes}"
    return url


def _request_precision_candidates(variant, params, countrycodes, use_cache=True):
    """
    Requests one structured Nominatim query variant and returns the raw list.

    Empty successful responses are negatively cached. Exceptions are never
    cached, matching the classic query behavior.
    """
    cache_key = precision_cache_key(
        variant, params, countrycodes, PRECISION_CACHE_VERSION
    )
    if use_cache:
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            if cached_result == NOMINATIM_NEGATIVE:
                return []
            return cached_result

    try:
        url = _build_nominatim_url(params, countrycodes)
        response = _get_nominatim(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            data = []
    except (requests.RequestException, ValueError) as e:
        print(
            "An error occurred while fetching precision location details for "
            f"{params!r}, countrycodes={countrycodes}: {e}"
        )
        return []

    if data:
        cache.set(cache_key, data, expire=get_ttl_seconds('nominatim'))
    else:
        negative_ttl = get_negative_ttl_seconds('nominatim')
        if negative_ttl > 0:
            cache.set(cache_key, NOMINATIM_NEGATIVE, expire=negative_ttl)

    return data


def query_nominatim_precision(location, place_name, postal_code, countrycodes, use_cache=True):
    """
    Tries structured query variants and returns the best matching candidate.

    The most specific variant is tried first. As soon as it yields a preferred
    result (a settlement when a place name is known, a postal code area when only
    a postal code is known), no further requests are made.

    Returns:
        tuple: (candidate dict or None, variant name or None)
    """
    best_candidate = None
    best_variant = None

    for variant, params in build_precision_queries(location, place_name, postal_code):
        data = _request_precision_candidates(
            variant, params, countrycodes, use_cache=use_cache
        )
        candidate = rank_nominatim_candidates(data, place_name, postal_code)
        if candidate is None:
            continue

        if (
            best_candidate is None
            or candidate_sort_key(candidate, place_name, postal_code)
            < candidate_sort_key(best_candidate, place_name, postal_code)
        ):
            best_candidate = candidate
            best_variant = variant

        if candidate_is_good_enough(candidate, place_name, postal_code):
            return candidate, variant

    return best_candidate, best_variant


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

def examine_locations(
    members,
    refresh_uids=(),
    strategy='precision',
    refresh_locations=False,
    precision_guard='disjoint',
):
    """
    Examines the locations of the members and updates their information.

    Args:
        members (dict): A dictionary containing the members' information.
        refresh_uids (iterable): UIDs whose Nominatim lookups must bypass the cache.
            Fresh results are still written to the cache.
        strategy (str): 'precision' (default) uses structured Nominatim queries
            and prefers settlements over postal code areas. 'classic' keeps the
            historical behavior.
        refresh_locations (bool): Bypass the Nominatim cache for every member.
        precision_guard (str): 'disjoint' keeps the classic result when the
            precision and classic areas do not overlap. 'old-radius' is the
            stricter variant that rejects every marker outside the classic
            circle. 'none' accepts every precision result. The classic result
            is read from the cache only, so the guard never triggers new
            requests.

    Returns:
        list: A list of updated members' information.
    """
    if strategy not in LOCATION_STRATEGIES:
        raise ValueError(
            f"Unknown location strategy {strategy!r}. "
            f"Valid values: {', '.join(LOCATION_STRATEGIES)}."
        )
    if precision_guard not in PRECISION_GUARDS:
        raise ValueError(
            f"Unknown precision guard {precision_guard!r}. "
            f"Valid values: {', '.join(PRECISION_GUARDS)}."
        )

    updated_members = []  # Initialize an empty list to store updated members' information
    total_members = len(members)  # Get the total number of members
    if isinstance(refresh_uids, str):
        refresh_uids = [refresh_uids]
    refresh_uids = {str(uid) for uid in (refresh_uids or ())}

    for index, uid in enumerate(members, start=1):
        member = members[uid]  # Get the member's information
        location = member.get('location', "").lower().strip()  # Get the member's location
        use_nominatim_cache = (not refresh_locations) and str(uid) not in refresh_uids

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
            match_metadata = None
            classic_fallback = False
            use_classic_radius = False

            if strategy == 'precision':
                if not location:
                    continue

                precision_postal_code = analyze_location_for_postal_code(location)
                place_name = extract_place_name(location, precision_postal_code, country_code)
                query_variant = None
                used_countrycodes = None

                fallback = None
                for cc_try in country_code_candidates(precision_postal_code, country_code):
                    candidate, candidate_variant = query_nominatim_precision(
                        location,
                        place_name,
                        precision_postal_code,
                        cc_try,
                        use_cache=use_nominatim_cache,
                    )
                    if candidate is None:
                        continue
                    if fallback is None:
                        fallback = (candidate, candidate_variant, cc_try)
                    if candidate_is_good_enough(
                        candidate, place_name, precision_postal_code
                    ):
                        nominatim_data = candidate
                        query_variant = candidate_variant
                        used_countrycodes = cc_try
                        break
                else:
                    if fallback is not None:
                        nominatim_data, query_variant, used_countrycodes = fallback

                classic_data = None
                classic_countrycodes = None
                for cc_try in country_code_candidates(precision_postal_code, country_code):
                    candidate = query_nominatim(
                        location,
                        cc_try,
                        use_cache=True,
                        cache_only=True,
                    )
                    if candidate and candidate_matches_location(
                        candidate, place_name, precision_postal_code
                    ):
                        classic_data = candidate
                        classic_countrycodes = cc_try
                        break

                selection_info = None
                if place_name and precision_postal_code and nominatim_data:
                    postcode_candidate = None
                    postcode_variant = None
                    postcode_countrycodes = None

                    if (
                        classic_data is not None
                        and is_postcode(classic_data)
                        and postcode_matches(classic_data, precision_postal_code)
                    ):
                        postcode_candidate = classic_data
                        postcode_variant = 'postcode_classic'
                        postcode_countrycodes = classic_countrycodes
                    else:
                        preferred_countrycode = None
                        address = nominatim_data.get('address')
                        if isinstance(address, dict):
                            preferred_countrycode = address.get('country_code')
                        if not preferred_countrycode:
                            preferred_countrycode = used_countrycodes
                        postcode_candidates = order_country_codes(
                            country_code_candidates(
                                precision_postal_code, country_code
                            ),
                            preferred_countrycode,
                        )
                        for cc_try in postcode_candidates:
                            data = _request_precision_candidates(
                                'postcode',
                                {'postalcode': precision_postal_code},
                                cc_try,
                                use_cache=use_nominatim_cache,
                            )
                            candidate = rank_nominatim_candidates(
                                data, '', precision_postal_code
                            )
                            if candidate is not None and is_postcode(candidate):
                                postcode_candidate = candidate
                                postcode_variant = 'postcode'
                                postcode_countrycodes = cc_try
                                break

                    if postcode_candidate is not None:
                        if is_postcode(nominatim_data):
                            chosen = postcode_candidate
                            chosen_variant = postcode_variant
                            chosen_countrycodes = postcode_countrycodes
                            selection_info = {'selection': 'only_postcode'}
                        else:
                            chosen, selection_info = choose_smaller_area(
                                nominatim_data, postcode_candidate
                            )
                            if chosen is postcode_candidate:
                                chosen_variant = postcode_variant
                                chosen_countrycodes = postcode_countrycodes
                            else:
                                chosen_variant = query_variant
                                chosen_countrycodes = used_countrycodes

                        nominatim_data = chosen
                        query_variant = chosen_variant
                        used_countrycodes = chosen_countrycodes
                        if is_postcode(nominatim_data):
                            use_classic_radius = True

                precision_data = nominatim_data
                if nominatim_data and precision_guard != 'none':
                    rejection = precision_rejection(
                        precision_data, classic_data, precision_guard
                    )
                    if rejection is not None:
                        match_metadata = summarize_candidate(
                            classic_data, 'classic_fallback', classic_countrycodes
                        )
                        match_metadata.update({
                            'strategy': 'classic_fallback',
                            'guard': precision_guard,
                            'guard_distance_m': rejection['distance_m'],
                            'guard_old_radius_m': rejection['old_radius_m'],
                            'guard_precision_radius_m': rejection['precision_radius_m'],
                            'guard_threshold_m': rejection['threshold_m'],
                            'selection': selection_info,
                            'rejected_precision': summarize_candidate(
                                precision_data, query_variant, used_countrycodes
                            ),
                        })
                        nominatim_data = classic_data
                        classic_fallback = True
                        use_classic_radius = True

                if nominatim_data and not classic_fallback:
                    match_metadata = summarize_candidate(
                        nominatim_data, query_variant, used_countrycodes
                    )
                    if selection_info:
                        match_metadata.update(selection_info)
            else:
                place_name = extract_place_name(location, postal_code, country_code)
                for cc_try in country_code_candidates(postal_code, country_code):
                    candidate = query_nominatim(
                        location,
                        cc_try,
                        use_cache=use_nominatim_cache,
                    )
                    if candidate and candidate_matches_location(
                        candidate, place_name, postal_code
                    ):
                        nominatim_data = candidate
                        break

            if nominatim_data:
                member['lat'] = nominatim_data.get('lat', 'N/A')  # Update member's latitude
                member['lon'] = nominatim_data.get('lon', 'N/A')  # Update member's longitude
                if strategy == 'precision' and not use_classic_radius:
                    member['radius'] = calculate_radius_from_point(
                        nominatim_data.get('boundingbox'),
                        nominatim_data.get('lat'),
                        nominatim_data.get('lon'),
                    )
                else:
                    member['radius'] = calculate_radius(nominatim_data.get('boundingbox'))  # Calculate radius
                if strategy == 'precision' and match_metadata is not None:
                    member['_location_match'] = match_metadata
            else:
                continue  # Continue to next member if no Nominatim data is found

            member['postal_code'] = postal_code  # Update member's postal code
            member['country_code'] = country_code  # Update member's country code
            updated_members.append(member)  # Add updated member to list

        print(f"Datensatz {index} / {total_members} verarbeitet")  # Print progress

    return updated_members  # Return list of updated members' information
