import json

from libs.data_scraper_lib import login, get_pages, download_members, parse_members, fetch_user_details
from libs.location_nominatim_lib import examine_locations

def main():

    login()
    members = download_members()
    print(f"Total members parsed: {len(members)}")  # Print the total number of members parsed

    # Save members to JSON file
    with open('tmp/members.json', 'w', encoding='utf-8') as jsonfile:
        json.dump(members, jsonfile, ensure_ascii=False, indent=4)

    # Read members.json
    with open('tmp/members.json', 'r', encoding='utf-8') as f:
        members = json.load(f)

    members_with_locations = examine_locations(members)
    with open('tmp/members_location.json', 'w', encoding='utf-8') as jsonfile:
        json.dump(members_with_locations, jsonfile, ensure_ascii=False, indent=4)

    vmforum_members = []
    for member in members_with_locations:
        vmforum_members.append({'id': member['uid'],
                                'name': member['name'],
                                'lat': member['lat'],
                                'lon': member['lon'],
                                'radius': member['radius'],
                                'vm': member.get('vm', None),
                                'tr': member.get('tr', None),
                                'lr': member.get('lr', None),
                                'other': member.get('other', None)})

    with open('vmforum_members.json', 'w', encoding='utf-8') as vmforumfile:
        json.dump(vmforum_members, vmforumfile, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main()
