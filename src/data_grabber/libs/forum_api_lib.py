import json
import os
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import diskcache as dc
import requests

from libs.cache_config_lib import get_ttl_seconds
from libs.paths_lib import CACHE_DIR, CONFIG_PATH
from libs.vehicle_label_lib import VEHICLE_FIELDS, VehicleLabelResolver, load_vehicle_label_map

cache = dc.Cache(str(CACHE_DIR))

CACHE_NAMESPACE = 'api-v1'
MEMBERS_DICT_CACHE_KEY = ('members_dict', CACHE_NAMESPACE)
MEMBERS_DICT_TTL = 60 * 60 * 24 - 60 * 60
LEGACY_USER_DETAILS_TTL = 60 * 60 * 24 * 14 - 60 * 60
INCOMPLETE_DETAILS_TTL = 60 * 60 * 24
UNKNOWN_VEHICLE_CACHE_KEY = ('vehicle_label_unknown', CACHE_NAMESPACE)
UNKNOWN_VEHICLE_TTL = 60 * 60 * 24 * 90

DEFAULT_API_TIMEOUT = 30
DEFAULT_API_MIN_INTERVAL = 0.25
DEFAULT_API_USER_AGENT = 'vmkarte/2.0 (+https://github.com/juefried/vmkarte)'

CUSTOM_FIELD_PATTERNS = {
    'vm': ('velomobil',),
    'lr': ('liegerad',),
    'tr': ('trike',),
    'other': ('sonstige', 'bemerkung', 'other'),
}

VEHICLE_LABEL_RESOLVER = VehicleLabelResolver(load_vehicle_label_map())
_RECORDED_VEHICLE_VALUES = set()

with CONFIG_PATH.open('r', encoding='utf-8') as f:
    config = json.load(f)

API_CONFIG = config.get('api') or {}
API_BASE_URL = (
    os.environ.get('XF_API_BASE_URL', '').strip()
    or str(API_CONFIG.get('base_url', '')).strip()
)
API_KEY = (
    os.environ.get('XF_API_KEY', '').strip()
    or str(API_CONFIG.get('api_key', '')).strip()
)
_raw_api_user_id = (
    os.environ.get('XF_API_USER_ID', '').strip()
    or str(API_CONFIG.get('api_user_id', '')).strip()
)
API_USER_ID = _raw_api_user_id if _raw_api_user_id.isdigit() else ''
API_USER_AGENT = (
    os.environ.get('XF_API_USER_AGENT', '').strip()
    or str(API_CONFIG.get('user_agent', '')).strip()
    or DEFAULT_API_USER_AGENT
)
CUSTOM_FIELD_MAP = {
    str(target): str(field_id)
    for target, field_id in (API_CONFIG.get('custom_field_map') or {}).items()
    if target in CUSTOM_FIELD_PATTERNS and str(field_id).strip()
}


class ForumApiError(RuntimeError):
    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class ForumApiAuthError(ForumApiError):
    pass


class ForumApiPermissionError(ForumApiError):
    pass


def _format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec='seconds')


def _now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _parse_error(response):
    code = ''
    message = response.text[:500]
    try:
        data = response.json()
        errors = data.get('errors') or []
        if errors:
            code = str(errors[0].get('code', ''))
            message = str(errors[0].get('message', message))
    except ValueError:
        pass

    if code in ('no_api_key_in_request', 'api_key_not_found'):
        return ForumApiAuthError(f"API-Key ungueltig: {message}", code, response.status_code)
    if code in ('do_not_have_permission', 'user_id_not_allowed'):
        return ForumApiPermissionError(
            f"Keine API-Berechtigung: {message}", code, response.status_code
        )
    return ForumApiError(
        f"API-Fehler {response.status_code}: {message}", code, response.status_code
    )


def _build_url(base_url, endpoint):
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


class ForumApiClient:
    def __init__(
        self,
        base_url,
        api_key,
        api_user_id='',
        user_agent=DEFAULT_API_USER_AGENT,
        timeout=DEFAULT_API_TIMEOUT,
        min_interval=DEFAULT_API_MIN_INTERVAL,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.api_user_id = api_user_id
        self.user_agent = user_agent
        self.timeout = timeout
        self.min_interval = max(0.0, float(min_interval))
        self._last_request_at = 0.0
        self._index = None

    def _headers(self):
        headers = {
            'XF-Api-Key': self.api_key,
            'Accept': 'application/json',
            'User-Agent': self.user_agent,
        }
        if self.api_user_id:
            headers['XF-Api-User'] = self.api_user_id
        return headers

    def _wait_for_slot(self):
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get(self, endpoint, params=None):
        if not self.api_key:
            raise ForumApiAuthError(
                "Kein API-Key konfiguriert. Bitte 'api.api_key' in config.json setzen."
            )
        if not self.base_url:
            raise ForumApiError(
                "Keine API-URL konfiguriert. Bitte 'api.base_url' in config.json setzen."
            )

        url = _build_url(self.base_url, endpoint)
        last_error = None

        for attempt in range(4):
            self._wait_for_slot()
            try:
                response = requests.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as error:
                last_error = ForumApiError(f"API-Anfrage fehlgeschlagen: {error}")
                if attempt == 3:
                    raise last_error from error
                time.sleep(2 ** attempt)
                continue
            finally:
                self._last_request_at = time.monotonic()

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as error:
                    raise ForumApiError(
                        f"Die API lieferte kein gueltiges JSON für '{endpoint}'."
                    ) from error

            error = _parse_error(response)
            last_error = error
            if (
                response.status_code == 429
                or 500 <= response.status_code < 600
                or (response.status_code == 400 and error.code == 'invalid_page')
            ):
                if attempt == 3:
                    raise error
                retry_after = response.headers.get('Retry-After', '')
                delay = int(retry_after) if retry_after.isdigit() else 2 ** attempt
                time.sleep(max(delay, 1))
                continue
            raise error

        raise last_error

    def get_index(self):
        if self._index is None:
            self._index = self.get('index/')
        return self._index

    def check_user_read(self):
        key = (self.get_index() or {}).get('key') or {}
        scopes = key.get('scopes') or []
        if isinstance(scopes, dict):
            allowed = bool(key.get('allow_all_scopes')) or bool(scopes.get('user:read'))
        else:
            allowed = bool(key.get('allow_all_scopes')) or 'user:read' in scopes
        if not allowed:
            raise ForumApiPermissionError(
                "Der API-Key hat keinen Scope 'user:read' und darf keine Benutzerdaten lesen."
            )
        return key

    def get_users_page(self, page):
        try:
            return self.get('users/', params={'page': page})
        except ForumApiPermissionError as error:
            key = {}
            try:
                key = (self.get_index() or {}).get('key') or {}
            except ForumApiError:
                pass
            key_type = key.get('type', 'unbekannt')
            raise ForumApiPermissionError(
                "Die Mitgliederliste ist mit diesem API-Key nicht lesbar "
                f"(Key-Typ: {key_type}). Benoetigt wird ein User-Key oder "
                "Super-User-Key fuer ein Konto, das die Mitgliederliste und "
                "Profile sehen darf, mit Scope 'user:read'.",
                error.code,
                error.status,
            ) from error

    def get_user(self, uid):
        return self.get(f'users/{uid}/')


_client = None


def get_client():
    global _client
    if _client is None:
        min_interval = API_CONFIG.get('min_interval_seconds', DEFAULT_API_MIN_INTERVAL)
        try:
            min_interval = float(min_interval)
        except (TypeError, ValueError):
            min_interval = DEFAULT_API_MIN_INTERVAL
        _client = ForumApiClient(
            API_BASE_URL,
            API_KEY,
            API_USER_ID,
            API_USER_AGENT,
            DEFAULT_API_TIMEOUT,
            min_interval,
        )
    return _client


def _extract_location(user):
    location = user.get('location')
    if not location and isinstance(user.get('profile'), dict):
        location = user['profile'].get('location')
    return location.strip() if isinstance(location, str) else ''


def _record_unknown_vehicle_value(target, raw, label, confidence, method):
    unknown = cache.get(UNKNOWN_VEHICLE_CACHE_KEY) or {}
    if not isinstance(unknown, dict):
        unknown = {}
    unknown[f'{target}\t{raw}'] = {
        'field': target,
        'raw': raw,
        'guess': label,
        'confidence': confidence,
        'method': method,
        'last_seen': _now(),
    }
    cache.set(UNKNOWN_VEHICLE_CACHE_KEY, unknown, expire=UNKNOWN_VEHICLE_TTL)


def _looks_like_raw_option(raw):
    return bool(raw) and ' ' not in raw and raw == raw.casefold()


def _display_vehicle_value(target, value):
    label, confidence, method = VEHICLE_LABEL_RESOLVER.resolve(target, value)
    raw = str(value).strip()

    if (
        target in VEHICLE_FIELDS
        and _looks_like_raw_option(raw)
        and not VEHICLE_LABEL_RESOLVER.is_known(target, raw)
    ):
        record_key = (target, raw)
        if record_key not in _RECORDED_VEHICLE_VALUES:
            _RECORDED_VEHICLE_VALUES.add(record_key)
            if method == 'humanized':
                print(
                    f"Warning: unknown vehicle option {target}={raw!r}; "
                    f"using best guess {label!r} ({method}, confidence {confidence:.2f}). "
                    "Add it to vehicle_label_map.json if the guess is wrong."
                )
            _record_unknown_vehicle_value(target, raw, label, confidence, method)

    return label


def _apply_custom_fields(member, custom_fields):
    if not isinstance(custom_fields, dict):
        return

    exact_map = {field_id: target for target, field_id in CUSTOM_FIELD_MAP.items()}

    for field_id, value in custom_fields.items():
        target = exact_map.get(str(field_id))
        if target is None:
            normalized = str(field_id).casefold()
            for candidate, patterns in CUSTOM_FIELD_PATTERNS.items():
                if any(pattern in normalized for pattern in patterns):
                    target = candidate
                    break
        if target and value not in (None, '', [], {}):
            member[target] = _display_vehicle_value(target, value)


def _normalize_vehicle_fields(member):
    for key in ('vm', 'lr', 'tr'):
        value = member.get(key)
        if value:
            member[key] = _display_vehicle_value(key, value)
    return member


def _member_from_user(user, details_from_list):
    uid = user.get('user_id')
    if uid is None:
        return None

    member = {
        'uid': str(uid),
        'name': str(user.get('username', '')),
    }

    location = _extract_location(user)
    if location:
        member['location'] = location

    href = user.get('view_url')
    if href:
        member['href'] = str(href)

    if details_from_list:
        for key in ('vm', 'lr', 'tr', 'other'):
            member.pop(key, None)
        _apply_custom_fields(member, user.get('custom_fields'))
        member['profile_updated_at'] = _now()
        member['_details_from_list'] = True

    return member


def _pagination_total_pages(pagination):
    if not isinstance(pagination, dict):
        return None
    total = (
        pagination.get('total_pages')
        or pagination.get('last_page')
        or pagination.get('page_count')
    )
    try:
        return int(total)
    except (TypeError, ValueError):
        return None


def get_members_dictionary(force_refresh=False):
    """
    Loads the member list through the XenForo REST API and caches it for 23 hours.

    The list endpoint is paginated. If a list entry includes custom_fields,
    those fields are used directly; otherwise fetch_user_details enriches that
    member individually.
    """
    if not force_refresh:
        cached_members = cache.get(MEMBERS_DICT_CACHE_KEY)
        if cached_members is not None:
            for member in cached_members.values():
                _normalize_vehicle_fields(member)
            return cached_members

    if force_refresh:
        print("Refreshing member list (members cache bypassed).")

    client = get_client()
    client.check_user_read()

    first_page = client.get_users_page(1)
    total_pages = _pagination_total_pages(first_page.get('pagination'))

    members_dict = {}
    page = 1
    while True:
        if page == 1:
            data = first_page
        else:
            try:
                data = client.get_users_page(page)
            except ForumApiError as error:
                if error.code == 'invalid_page' and page > 1 and members_dict:
                    print(
                        f"Warning: API reports invalid page {page}; "
                        "treating member list as complete."
                    )
                    break
                raise

        users = data.get('users') or []
        print(f"Processing member list page {page}/{total_pages or '?'}...")
        for user in users:
            member = _member_from_user(user, 'custom_fields' in user)
            if member:
                members_dict[member['uid']] = member

        if total_pages is not None:
            if page >= total_pages:
                break
        elif not users:
            break
        elif page >= 1000:
            raise ForumApiError("Die Mitgliederliste ueberschreitet 1000 Seiten; Abbruch.")
        page += 1

    if members_dict:
        cache.set(MEMBERS_DICT_CACHE_KEY, members_dict, expire=MEMBERS_DICT_TTL)
    else:
        raise ForumApiError(
            "Die API lieferte eine leere Mitgliederliste; der Cache wurde nicht aktualisiert."
        )

    return members_dict


def resolve_refresh_targets(tokens, members_dict):
    """
    Resolves refresh tokens (UIDs or exact member names) to member UIDs.
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


def fetch_user_details(member, force_refresh=False):
    """
    Fetches a user from the API and caches the enriched member object.

    If the API does not expose custom_fields, the existing vehicle fields are
    preserved and the result is cached with a short TTL so permissions can be
    fixed without waiting for the normal 7-14 day TTL.
    """
    uid = str(member['uid'])
    cache_key = ('user_details', CACHE_NAMESPACE, uid)

    if not force_refresh:
        cached_entry = cache.get(cache_key, expire_time=True)
        if cached_entry is None:
            cached_member, expire_time = None, None
        else:
            cached_member, expire_time = cached_entry
        if cached_member is not None:
            if not cached_member.get('profile_updated_at') and expire_time is not None:
                cached_member['profile_updated_at'] = _format_timestamp(
                    expire_time - LEGACY_USER_DETAILS_TTL
                )
            return _normalize_vehicle_fields(cached_member)

        if member.get('_details_from_list'):
            _normalize_vehicle_fields(member)
            member.setdefault('profile_updated_at', _now())
            cache.set(cache_key, member, expire=get_ttl_seconds('user_details'))
            return member

    client = get_client()
    try:
        data = client.get_user(uid)
    except ForumApiPermissionError as error:
        print(
            f"Warning: no permission to read profile {uid}: {error}. "
            "Keeping existing data and using a short cache TTL."
        )
        ttl = min(get_ttl_seconds('user_details'), INCOMPLETE_DETAILS_TTL)
        _normalize_vehicle_fields(member)
        cache.set(cache_key, member, expire=ttl)
        return member
    except ForumApiError as error:
        print(f"An error occurred while fetching user {uid}: {error}")
        return member

    user = data.get('user') or {}
    updated = dict(member)
    updated['uid'] = uid
    updated['name'] = str(user.get('username', member.get('name', '')))

    location = _extract_location(user)
    if location:
        updated['location'] = location
    else:
        updated.pop('location', None)

    href = user.get('view_url')
    if href:
        updated['href'] = str(href)

    has_custom_fields = 'custom_fields' in user
    if has_custom_fields:
        for key in ('vm', 'lr', 'tr', 'other'):
            updated.pop(key, None)
        _apply_custom_fields(updated, user.get('custom_fields'))

    updated['profile_updated_at'] = _now()
    updated.pop('_details_from_list', None)

    ttl = get_ttl_seconds('user_details')
    if not has_custom_fields:
        print(
            f"Warning: API response for user {uid} has no custom_fields. "
            "Vehicle fields are kept from the existing data; short cache TTL is used."
        )
        ttl = min(ttl, INCOMPLETE_DETAILS_TTL)

    cache.set(cache_key, updated, expire=ttl)
    return updated


def get_member_data(refresh_members=False, refresh_user_tokens=()):
    """
    Retrieves all member data through the API and returns the enriched dictionary.
    """
    if isinstance(refresh_user_tokens, str):
        refresh_user_tokens = [refresh_user_tokens]
    refresh_user_tokens = refresh_user_tokens or ()
    tokens = [token.strip() for token in refresh_user_tokens if token and token.strip()]

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
            messages.append("Refresh target(s) not found: " + ', '.join(unresolved))
        for token, matches in ambiguous.items():
            messages.append(f"Refresh target '{token}' is ambiguous: {', '.join(matches)}")
        raise SystemExit('; '.join(messages))

    num_members = len(members_dict)
    for i, uid in enumerate(members_dict, start=1):
        member = members_dict[uid]
        print(f'Processing Member {i} / {num_members} ({member.get("name", uid)})')

        force_refresh = str(uid) in refresh_uids
        if force_refresh:
            print(
                f'Refreshing profile for {member.get("name", uid)} ({uid}); '
                'user and Nominatim caches bypassed'
            )

        members_dict[uid] = fetch_user_details(member, force_refresh=force_refresh)

    return members_dict, refresh_uids
