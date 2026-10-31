#!/usr/bin/python3

"""
Local smoke test for the XenForo REST API and Nominatim integration.

Run this from src/data_grabber so that config.json and libs/ are found.
It checks the API key, one user profile and one member list page, then resolves
up to two locations. It does not write members.json or vmforum_members.json.
"""

from libs.forum_api_lib import (
    ForumApiError,
    ForumApiPermissionError,
    fetch_user_details,
    get_client,
)
from libs.location_nominatim_lib import examine_locations


def _member_from_api_user(user):
    uid = user.get('user_id')
    if uid is None:
        return None
    member = {
        'uid': str(uid),
        'name': str(user.get('username', '')),
    }
    location = user.get('location')
    if location:
        member['location'] = str(location)
    return member


def main():
    client = get_client()

    print("1) API-Index ...")
    index = client.get_index()
    key = index.get('key') or {}
    print(f"   {index.get('site_title')} / {index.get('api_url')}")
    print(f"   Key-Typ: {key.get('type')}, Scopes: {key.get('scopes')}")
    client.check_user_read()
    print("   user:read OK")

    print("2) Einzelprofil (User 1) ...")
    try:
        data = client.get_user(1)
        user = data.get('user') or {}
        has_custom_fields = 'custom_fields' in user
        print(
            "   location vorhanden: "
            f"{'location' in user}, custom_fields vorhanden: "
            f"{has_custom_fields}"
        )
        if not has_custom_fields:
            print(
                "   Hinweis: Der Key-Kontext sieht keine custom_fields; "
                "die Fahrzeugfelder fehlen."
            )
    except ForumApiError as error:
        print(f"   FEHLER: {error}")

    print("3) Mitgliederliste (Seite 1) ...")
    try:
        page = client.get_users_page(1)
    except ForumApiPermissionError as error:
        raise SystemExit(f"   FEHLER: {error}")
    except ForumApiError as error:
        raise SystemExit(f"   FEHLER: {error}")

    users = page.get('users') or []
    print(f"   Mitglieder auf Seite 1: {len(users)}")

    members = [m for m in (_member_from_api_user(u) for u in users) if m and m.get('location')]
    if not members:
        print("   Keine Mitglieder mit Ortsangabe auf Seite 1 gefunden.")
        return

    detailed_members = []
    for member in members[:2]:
        print(f"4) Profil laden: UID {member['uid']} ...")
        detailed = fetch_user_details(dict(member), force_refresh=True)
        print(
            "   location: "
            f"{bool(detailed.get('location'))}, Fahrzeugfelder: "
            f"{[key for key in ('vm', 'lr', 'tr', 'other') if detailed.get(key)]}"
        )
        detailed_members.append(detailed)

    print("5) Nominatim-Abfrage ...")
    result = examine_locations({member['uid']: member for member in detailed_members})
    print(f"   Aufgeloeste Datensätze: {len(result)}")
    for entry in result:
        print(
            f"   UID {entry['uid']}: lat={entry.get('lat')}, "
            f"lon={entry.get('lon')}, radius={entry.get('radius')}, "
            f"profile_updated_at={entry.get('profile_updated_at')}"
        )

    if not result:
        raise SystemExit("Smoke test fehlgeschlagen: keine Koordinaten ermittelt.")

    print("Smoke test OK")


if __name__ == "__main__":
    main()
