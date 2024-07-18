import json
import requests
from bs4 import BeautifulSoup
import diskcache as dc

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
    try:
        # Get the login page to retrieve the _xfToken
        login_page = session.get('https://www.velomobilforum.de/forum/index.php?login/login', headers=headers)
        login_page.raise_for_status()
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
        response = session.post('https://www.velomobilforum.de/forum/index.php?login/login', data=payload, headers=headers)
        response.raise_for_status()
        if 'Log in' in response.text:
            raise Exception("Login failed, please check your credentials.")
    except Exception as e:
        print(f"An error occurred during login: {e}")
        raise


def get_members_from_dictionary_soup(soup):
    members = []
    for user in soup.select('h3.contentRow-header a.username'):
        member = {
            'uid': user['data-user-id'],
            'name': user.get_text()
        }

        content_row_main = user.find_parent('div', class_='contentRow-main')
        location_div = content_row_main.find('div', class_='contentRow-lesser')
        if location_div and location_div.find('a'):
            member['location'] = location_div.find('a').get_text()
        member['href'] = user['href']
        members.append(member)
    return members

@cache.memoize(name='members_dict', expire=60*60*24*14-60*60)
def get_members_dictionary():

    members_dict = {}

    #get number of dictionary pages by retreiving first page
    pages = 1 # default

    try:
        # Retrieve the first page to determine the number of pages
        print(f"Getting number of pages...")
        page = session.get('https://www.velomobilforum.de/forum/index.php?members/list/', headers=headers)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')
        pages_numbers = [int(a.text) for a in soup.select('ul.pageNav-main li.pageNav-page a') if a.text.isdigit()]
        pages = max(pages_numbers) if pages_numbers else 1
    except Exception as e:
        print(f"An error occurred while retrieving pages: {e}")

    #iterate over all other dictionary pages
    for i in range (1, pages +1):
        print(f"Processing member list page {i}/{pages}...")
        try:
            page = session.get(f'https://www.velomobilforum.de/forum/index.php?members/list/&page={i}', headers=headers)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, 'html.parser')
            members = get_members_from_dictionary_soup(soup)
            for member in members:
                members_dict[member['uid']] = member
        except Exception as e:
            print(f"An error occurred while downloading page {page}: {e}")

    return members_dict

def get_member_data():
    login()
    members_dict = get_members_dictionary()

    num_members = len(members_dict)
    for i, uid in enumerate(members_dict, start=1):
        member = members_dict[uid]
        print(f'Processing Member "{member['name']}" {i}/{num_members}')
        member = {key: member[key] for key in sorted(member)}
        members_dict[uid]=fetch_user_details(member)
    return members_dict


def fetch_user_details(member):
    profile_url = f"https://www.velomobilforum.de{member['href']}about"

    # Check if the entry exists in the cache
    cache_key = ('user_details', member['uid'])
    if cache_key in cache:
        return cache[cache_key]

    try:
        response = session.get(profile_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        dl_elements = soup.find_all('dl', class_='pairs--columns')
        for dl in dl_elements:
            dt = dl.find('dt').text.strip()
            dd = dl.find('dd').text.strip()

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

