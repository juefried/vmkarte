import json
import requests
from bs4 import BeautifulSoup
import diskcache as dc
from typing import List, Dict

cache = dc.Cache('cache')

# Read configuration file
with open('config.json', 'r', encoding='utf-8') as f:
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


@cache.memoize(name='members_dict', expire=60*60*24-60*60)
def get_members_dictionary():
    """
    Retrieves a dictionary of members from the Velomobilforum website.

    The dictionary is memoized with the name 'members_dict' and expires after 23 hours.

    Returns:
        dict: A dictionary where the keys are the member IDs and the values are dictionaries
              containing member information.
    """

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

    return members_dict


def get_member_data():
    """
    Retrieves member data by logging in, getting the member dictionary,
    fetching user details for each member, and returning the updated member dictionary.

    Returns:
        dict: A dictionary where the keys are the member IDs and the values are dictionaries
              containing updated member information.
    """
    # Log in to the website
    login()

    # Get the member dictionary
    members_dict = get_members_dictionary()

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

        # Fetch user details for the member
        members_dict[uid] = fetch_user_details(member)

    # Return the updated member dictionary
    return members_dict



def fetch_user_details(member):
    """
    Fetches user details from the Velomobilforum website and updates the member dictionary.

    Args:
        member (dict): A dictionary containing member information.

    Returns:
        dict: A dictionary containing updated member information.

    Raises:
        Exception: If an error occurs during the fetch process.
    """
    # Construct the profile URL
    profile_url = f"https://www.velomobilforum.de{member['href']}about"

    # Check if the entry exists in the cache
    cache_key = ('user_details', member['uid'])
    if cache_key in cache:
        return cache[cache_key]

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
        cache.set(cache_key, member, expire=60*60*24*14-60*60)

    except Exception as e:
        print(f"An error occurred while fetching user details from {profile_url}: {e}")

    return member


