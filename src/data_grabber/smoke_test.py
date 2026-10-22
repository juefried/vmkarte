#!/usr/bin/python3

"""
Local smoke test for the forum scraper and Nominatim integration.

Run this from src/data_grabber so that config.json and libs/ are found.
It logs in, parses one member list page, fetches a few profiles and resolves
two locations. It does not write members.json or vmforum_members.json.
"""

from bs4 import BeautifulSoup

from libs.data_scraper_lib import (
    fetch_user_details,
    get_members_from_dictionary_soup,
    headers,
    login,
    session,
)
from libs.location_nominatim_lib import examine_locations


def main():
    print("1) Login ...")
    login()
    print("   Login OK")

    print("2) Mitgliederliste laden ...")
    page = session.get(
        "https://www.velomobilforum.de/forum/index.php?members/list/",
        headers=headers,
        timeout=30,
    )
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    members = get_members_from_dictionary_soup(soup)
    print(f"   Mitglieder auf Seite 1: {len(members)}")

    members_with_location = [member for member in members if member.get("location")]
    if not members_with_location:
        print("   Keine Mitglieder mit Ortsangabe auf Seite 1 gefunden.")
        return

    detailed_members = []
    for member in members_with_location[:2]:
        print(f"3) Profil laden: {member['name']} ({member['uid']}) ...")
        detailed = fetch_user_details(dict(member))
        print(f"   {detailed}")
        detailed_members.append(detailed)

    print("4) Nominatim-Abfrage ...")
    result = examine_locations({member["uid"]: member for member in detailed_members})
    print(f"   Aufgelöste Datensätze: {len(result)}")
    for entry in result:
        print(
            f"   {entry['name']}: lat={entry.get('lat')}, "
            f"lon={entry.get('lon')}, radius={entry.get('radius')}"
        )

    if not result:
        raise SystemExit("Smoke test fehlgeschlagen: keine Koordinaten ermittelt.")

    print("Smoke test OK")


if __name__ == "__main__":
    main()
