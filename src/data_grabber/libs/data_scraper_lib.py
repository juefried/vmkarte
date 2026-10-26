import json
from datetime import datetime
from typing import List, Dict

import requests
from bs4 import BeautifulSoup
import diskcache as dc

from libs.cache_config_lib import get_ttl_seconds
from libs.paths_lib import CACHE_DIR, CONFIG_PATH

cache = dc.Cache(str(CACHE_DIR))

MEMBERS_DICT_CACHE_KEY = ('members_dict',)
MEMBERS_DICT_TTL = 60 * 60 * 24 - 60 * 60
LEGACY_USER_DETAILS_TTL = 60 * 60 * 24 * 14 - 60 * 60


def _format_timestamp(timestamp):
    """
    Formats a POSIX timestamp as an ISO 8601 string in the local timezone.
    """
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec='seconds')


# Read configuration file
with CONFIG_PATH.open('r', encoding='utf-8') as f:
    config = json.load(f)

# Login data to velomobilforum.de
USERNAME = config['username']
PASSWORD = config['password']

# Start a session
session = requests.Session()

# Headers to mimic a browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def login():
    """
    Logs in to the website using the provided credentials.

    Raises:
        Exception: If login fails or an error occurs during the login process.
    """
    try:
        # Get the login page to retrieve the _xfToken

        login_url = 'https://www.velomobilforum.de/forum/index.php?login/login'
        login_page = session.get(login_url, headers=headers)
        login_page.raise_for_status()

        # Parse the login page HTML to extract the _xfToken
        soup = BeautifulSoup(login_page.text, 'html.parser')
        token = soup.find('input', {'name': '_xfToken'})['value']

        # Perform login
        payload = {
            'login': USERNAME,
            'password': PASSWORD,
            'remember': '1',
            '_xfRedirect': 'https://www.velomobilforum.de/forum/index.php',
            '_xfToken': token
        }

        login_post_url = 'https://www.velomobilforum.de/forum/index.php?login/login'
        response = session.post(login_post_url, data=payload, headers=headers)
        response.raise_for_status()

        # Check if the login was successful
        if 'Log in' in response.text:
            raise Exception("Login failed, please check your credentials.")
    except Exception as e:
        print(f"An error occurred during login: {e}")
        raise


def get_members_from_dictionary_soup(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Extracts members information from a BeautifulSoup object.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object representing the HTML content.

    Returns:
        List[Dict[str, str]]: A list of dictionaries containing member information.
            Each dictionary contains the following keys:
            - 'uid': The user ID.
            - 'name': The member name.
            - 'location': The member location (if available).
            - 'href': The member link.

    """
    members = []
    for user in soup.select('h3.contentRow-header a.username'):
        member = {
            'uid': user['data-user-id'],

            'name': user.get_text(),
        }

        # Find the parent div with class 'contentRow-main'
        content_row_main = user.find_parent('div', class_='contentRow-main')

        # Find the div with class 'contentRow-lesser' inside the parent div
        location_div = content_row_main.find('div', class_='contentRow-lesser')

        # If the location div exists and contains an anchor tag, extract the location
        if location_div and location_div.find('a'):
            member['location'] = location_div.find('a').get_text()

        # Store the member link
        member['href'] = user['href']

        members.append(member)
    return members


def get_members_dictionary(force_refresh=False):
    """
    Retrieves a dictionary of members from the Velomobilforum website.

    The result is cached under 'members_dict' for 23 hours. With force_refresh
    the cached entry is ignored and replaced. Empty results are not cached so a
    failed login cannot poison an existing member list.

    Args:
        force_refresh (bool): Ignore the cached member list and scrape it again.

    Returns:
        dict: A dictionary where the keys are the member IDs and the values are dictionaries
              containing member information.
    """
    if not force_refresh:
        cached_members = cache.get(MEMBERS_DICT_CACHE_KEY)
        if cached_members is not None:
            return cached_members

    if force_refresh:
        print("Refreshing member list (members cache bypassed).")

    members_dict = {}

    # Get the number of dictionary pages by retrieving the first page
    pages = 1  # default

    try:
        # Retrieve the first page to determine the number of pages
        print("Getting number of pages...")
        page = session.get('https://www.velomobilforum.de/forum/index.php?members/list/', headers=headers)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')

        # Extract the page numbers from the HTML
        pages_numbers = [int(a.text) for a in soup.select('ul.pageNav-main li.pageNav-page a') if a.text.isdigit()]
        pages = max(pages_numbers) if pages_numbers else 1
    except Exception as e:
        print(f"An error occurred while retrieving pages: {e}")

    # Iterate over all other dictionary pages
    for i in range(1, pages + 1):
        print(f"Processing member list page {i}/{pages}...")
        try:
            # Retrieve the HTML content of the current page
            page = session.get(f'https://www.velomobilforum.de/forum/index.php?members/list/&page={i}', headers=headers)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, 'html.parser')

            # Extract the member information from the HTML
            members = get_members_from_dictionary_soup(soup)

            # Add the member information to the dictionary
            for member in members:
                members_dict[member['uid']] = member
        except Exception as e:
            print(f"An error occurred while downloading page {page}: {e}")

    if members_dict:
        cache.set(MEMBERS_DICT_CACHE_KEY, members_dict, expire=MEMBERS_DICT_TTL)
    else:
        print("Member list is empty; the members cache was not updated.")

    return members_dict


def resolve_refresh_targets(tokens, members_dict):
    """
    Resolves refresh tokens (UIDs or exact member names) to member UIDs.

    Args:
        tokens (iterable): UIDs or exact forum names.
        members_dict (dict): The currently available member dictionary.

    Returns:
        tuple: A set of resolved UIDs, a list of unresolved tokens and a dict
            mapping ambiguous tokens to their matching UIDs.
    """
    resolved_uids = set()
    unresolved = []
    ambiguous = {}

    names = {}
    for uid, member in members_dict.items():
        name = str(member.get('name', '')).casefold()
        names.setdefault(name, []).append(str(uid))

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        if token.isdigit() and token in members_dict:
            resolved_uids.add(token)
            continue

        matches = names.get(token.casefold(), [])
        if len(matches) == 1:
            resolved_uids.add(matches[0])
        elif len(matches) > 1:
            ambiguous[token] = matches
        else:
            unresolved.append(token)

    return resolved_uids, unresolved, ambiguous


def get_member_data(refresh_members=False, refresh_user_tokens=()):
    """
    Retrieves member data by logging in, getting the member dictionary,
    fetching user details for each member, and returning the updated member dictionary.

    Args:
        refresh_members (bool): Ignore the cached member list and reload it.
        refresh_user_tokens (iterable): UIDs or exact member names whose profile
            data should be refreshed even if a cached entry exists.

    Returns:
        tuple: The updated member dictionary and the set of refreshed UIDs.
    """
    if isinstance(refresh_user_tokens, str):
        refresh_user_tokens = [refresh_user_tokens]
    refresh_user_tokens = refresh_user_tokens or ()
    tokens = [token.strip() for token in refresh_user_tokens if token and token.strip()]

    # Log in to the website
    login()

    # Get the member dictionary
    members_dict = get_members_dictionary(force_refresh=refresh_members)

    refresh_uids, unresolved, ambiguous = resolve_refresh_targets(tokens, members_dict)
    if unresolved and not refresh_members:
        print(
            "Refresh target(s) not found in the cached member list: "
            f"{', '.join(unresolved)}. Reloading member list..."
        )
        members_dict = get_members_dictionary(force_refresh=True)
        refresh_uids, unresolved, ambiguous = resolve_refresh_targets(tokens, members_dict)

    if unresolved or ambiguous:
        messages = []
        if unresolved:
            messages.append(
                "Refresh target(s) not found: " + ', '.join(unresolved)
            )
        for token, matches in ambiguous.items():
            messages.append(
                f"Refresh target '{token}' is ambiguous: {', '.join(matches)}"
            )
        raise SystemExit('; '.join(messages))

    # Get the number of members
    num_members = len(members_dict)

    # Iterate over each member in the member dictionary
    for i, uid in enumerate(members_dict, start=1):
        # Get the member details
        member = members_dict[uid]

        # Print the progress
        print(f'Processing Member {i} / {num_members} ({member["name"]})')

        # Sort the member details
        member = {key: member[key] for key in sorted(member)}

        force_refresh = str(uid) in refresh_uids
        if force_refresh:
            print(
                f'Refreshing profile for {member["name"]} ({uid}); '
                'user and Nominatim caches bypassed'
            )

        # Fetch user details for the member
        members_dict[uid] = fetch_user_details(member, force_refresh=force_refresh)

    # Return the updated member dictionary and the resolved refresh targets
    return members_dict, refresh_uids



def fetch_user_details(member, force_refresh=False):
    """
    Fetches user details from the Velomobilforum website and updates the member dictionary.

    Args:
        member (dict): A dictionary containing member information.
        force_refresh (bool): Ignore the cached entry and fetch the profile page again.

    Returns:
        dict: A dictionary containing updated member information.

    Raises:
        Exception: If an error occurs during the fetch process.
    """
    # Construct the profile URL
    profile_url = f"https://www.velomobilforum.de{member['href']}about"

    # Check if the entry exists in the cache unless a refresh was requested
    cache_key = ('user_details', member['uid'])
    if not force_refresh:
        cached_member, expire_time = cache.get(cache_key, expire_time=True)

        if cached_member is not None:
            if not cached_member.get('profile_updated_at') and expire_time is not None:
                cached_member['profile_updated_at'] = _format_timestamp(
                    expire_time - LEGACY_USER_DETAILS_TTL
                )
            return cached_member

    try:
        # Fetch the profile page
        response = session.get(profile_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all the dl elements with class 'pairs--columns'
        dl_elements = soup.find_all('dl', class_='pairs--columns')

        # Iterate over each dl element
        for dl in dl_elements:
            dt = dl.find('dt').text.strip()
            dd = dl.find('dd').text.strip()

            # Update the member dictionary based on the dt value
            if dt == "Velomobil":
                member['vm'] = dd
            elif dt == "Liegerad":
                member['lr'] = dd
            elif dt == "Trike":
                member['tr'] = dd
            elif dt == "sonstige Fahrzeuge/Bemerkungen":
                member['other'] = dd

        # Save the result in the cache
        member['profile_updated_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
        cache.set(cache_key, member, expire=get_ttl_seconds('user_details'))

    except Exception as e:
        print(f"An error occurred while fetching user details from {profile_url}: {e}")

    return member


