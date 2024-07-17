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

def get_pages():
    try:
        # Retrieve the first page to determine the number of pages
        page = session.get('https://www.velomobilforum.de/forum/index.php?members/list/', headers=headers)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')
        pages = [int(a.text) for a in soup.select('ul.pageNav-main li.pageNav-page a') if a.text.isdigit()]
        return max(pages) if pages else 1
    except Exception as e:
        print(f"An error occurred while retrieving pages: {e}")
        return 1

def download_members():
    pages = get_pages()
    members = []

    for i in range(1, pages + 1):
        print(f"Processing member list page {i}/{pages} ...")
        members.extend(download_page(i))
    return members

@cache.memoize(name='member_page', expire=60*60*23)
def download_page(page):
    try:
        page = session.get(f'https://www.velomobilforum.de/forum/index.php?members/list/&page={page}', headers=headers)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')
        return parse_members(soup)
    except Exception as e:
        print(f"An error occurred while downloading page {page}: {e}")

def parse_members(soup):
    members = []

    for user in soup.select('h3.contentRow-header a.username'):
        member_data = {
            'uid': user['data-user-id'],
            'name': user.get_text()
        }

        content_row_main = user.find_parent('div', class_='contentRow-main')
        location_div = content_row_main.find('div', class_='contentRow-lesser')
        if location_div and location_div.find('a'):
            member_data['location'] = location_div.find('a').get_text()

        profile_url = f"https://www.velomobilforum.de{user['href']}about"
        user_details = fetch_user_details(profile_url, member_data)

        members.append(user_details)
    return members

@cache.memoize(name='user_details', expire=60*60*23)
def fetch_user_details(profile_url, member):
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
    except Exception as e:
        print(f"An error occurred while fetching user details from {profile_url}: {e}")
    return member