import json

from libs.data_scraper_lib import login, get_pages, download_members, parse_members, fetch_user_details
from libs.location_nominatim_lib import examine_locations

def main():

    login()
    members = download_members()
    print(f"Total members parsed: {len(members)}")  # Print the total number of members parsed

    members = examine_locations(members)

    vmforum_members = []
    for member in members:
        data = {'id': member['uid'],
                'name': member['name'],
                'lat': member['lat'],
                'lon': member['lon'],
                'radius': member['radius']}
        for key in ['vm', 'tr', 'lr', 'other']:
            if member.get(key):
                data[key] = member[key]

        vmforum_members.append(data)

    with open('../www_data/vmforum_members.json', 'w', encoding='utf-8') as vmforumfile:
        json.dump(vmforum_members, vmforumfile, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
