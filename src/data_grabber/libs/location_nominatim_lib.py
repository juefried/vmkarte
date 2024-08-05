"""
python location_nominatim_lib.py
"""
import json
import time

import requests
from urllib.parse import quote
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


@cache.memoize(name='nominatim', expire=60*60*24*365-60*60)
def query_nominatim(searchstring, country_code):
    """
    Memoized function that queries the Nominatim API for location details based on the search string and country code.

    Args:
        searchstring (str): The location to search for.
        country_code (str): The country code to narrow down the search, can be None.

    Returns:
        dict or None: The location details if found, otherwise None.
    """
    # Check if searchstring is None
    if searchstring is None:
        return None

    # Remove leading and trailing commas and spaces from searchstring
    searchstring = searchstring.strip(', ')

    try:
        # Check if country_code is not None
        if country_code is not None:
            # Check if searchstring matches the pattern '^[a-z]{1,3}-(\d{4,5}.*)$'
            match = re.match(r'^[a-z]{1,3}-(\d{4,5}.*)$', searchstring)
            if match:
                # Extract the matched group from searchstring
                searchstring = match.group(1)

        # Construct the URL for the Nominatim API request
        url = f"https://nominatim.openstreetmap.org/search?q={quote(searchstring)}&format=json&addressdetails=1&email={EMAIL}"
        if country_code is not None:
            # Add the country code to the URL
            url += f"&countrycodes={country_code}"

        # Send a GET request to the Nominatim API
        response = requests.get(url)

        # Sleep for 1 second to avoid overwhelming the API with requests
        time.sleep(1)
        # Raise an exception if the response status code is not 200
        response.raise_for_status()
        # Parse the response JSON data
        data = response.json()

        if len(data) == 1:
            # Perform another search excluding the found place ID
            exclude_place_id = data[0]['place_id']
            url_exclude = f"{url}&exclude_place_ids={exclude_place_id}"
            response_exclude = requests.get(url_exclude)

            # Sleep for 1 second to avoid overwhelming the API with requests
            time.sleep(1)
            response_exclude.raise_for_status()
            data_exclude = response_exclude.json()

            # Add the new data to the original data
            data.extend(data_exclude)

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
                        return entry

            # If no match is found, return the first entry in the data
            return data[0]

    except requests.RequestException as e:
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

def examine_locations(members):
    """
    Examines the locations of the members and updates their information.

    Args:
        members (dict): A dictionary containing the members' information.

    Returns:
        list: A list of updated members' information.
    """
    updated_members = []  # Initialize an empty list to store updated members' information
    total_members = len(members)  # Get the total number of members

    for index, uid in enumerate(members, start=1):
        member = members[uid]  # Get the member's information
        location = member.get('location', "").lower().strip()  # Get the member's location

        postal_code = None  # Initialize variable to store postal code
        country_code = None  # Initialize variable to store country code

        if location:
            country_code = analyze_location_for_country(location)  # Analyze location for country code
            postal_code = analyze_location_for_postal_code(location)  # Analyze location for postal code
            new_location = prepare_location(location)  # Prepare location for query
            if country_code is None and new_location != location:
                country_code = analyze_location_for_country(new_location)  # Analyze new location for country code
            location = new_location  # Update location

            nominatim_data = None  # Initialize variable to store Nominatim data

            if country_code is not None:
                nominatim_data = query_nominatim(location, country_code)  # Query Nominatim with country code
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
                    nominatim_data = query_nominatim(location, cc_try)  # Query Nominatim with country code try
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
