"""
Pure helpers for the opt-in precision location strategy.

The functions in this module do not perform any network or cache access so they
can be tested in isolation. The Nominatim request layer lives in
``location_nominatim_lib``.
"""

import re
import unicodedata

from geopy.distance import geodesic

from libs.location_mapping_rules_lib import country_mapping_reverse

PRECISION_CACHE_VERSION = 'precision-v1'


def precision_cache_key(variant, params, countrycodes, version):
    """
    Builds a cache key for a structured precision query.

    The version and variant are part of the key so classic free-form results can
    never satisfy a precision query.
    """
    return (
        'nominatim',
        version,
        variant,
        tuple(sorted(params.items())),
        countrycodes,
    )


CITY_ADDRESSTYPES = {'city', 'town'}
AREA_ADDRESSTYPES = {
    'region',
    'state',
    'county',
    'province',
    'district',
    'municipality',
}
VILLAGE_ADDRESSTYPES = {
    'village',
    'hamlet',
    'suburb',
    'neighbourhood',
    'quarter',
    'borough',
    'isolated_dwelling',
    'locality',
}
SETTLEMENT_ADDRESSTYPES = (
    CITY_ADDRESSTYPES | AREA_ADDRESSTYPES | VILLAGE_ADDRESSTYPES
)

ADMIN_NAME_PREFIXES = {
    'landkreis',
    'kreis',
    'stadt',
    'gemeinde',
    'region',
    'bezirk',
    'county',
    'district',
    'municipality',
    'markt',
    'flecken',
    'amt',
    'province',
    'state',
}


def is_postcode(entry):
    """Returns True if the Nominatim entry describes a postal code area."""
    if not isinstance(entry, dict):
        return False
    return entry.get('type') == 'postal_code' or entry.get('addresstype') == 'postcode'


def is_settlement(entry):
    """Returns True if the Nominatim entry describes a populated place."""
    if not isinstance(entry, dict):
        return False
    return (
        entry.get('type') in SETTLEMENT_ADDRESSTYPES
        or entry.get('addresstype') in SETTLEMENT_ADDRESSTYPES
    )


def extract_place_name(location, postal_code, country_code):
    """
    Removes postal code and country tokens from a prepared location string.

    Args:
        location (str): Prepared location string (already lowercased).
        postal_code (str): Postal code extracted from the location, or None.
        country_code (str): Detected country code, or None.

    Returns:
        str: The remaining place name, possibly empty.
    """
    text = ' '.join((location or '').strip().split())
    if not text:
        return ''

    if country_code is not None:
        text = re.sub(r'^[a-z]{1,3}-(?=\d{4,5})', '', text)

    if postal_code:
        text = re.sub(
            r'(?<!\d)' + re.escape(str(postal_code)) + r'(?!\d)',
            ' ',
            text,
        )

    head = re.split(r'[,;]', text, maxsplit=1)[0].strip()
    if head:
        text = head

    if country_code is not None:
        without_country = text
        for name, code in country_mapping_reverse.items():
            if code == country_code and len(name) >= 3:
                without_country = re.sub(
                    r'\b' + re.escape(name) + r'\b', ' ', without_country
                )
        without_country = without_country.strip(' ,;/')
        if without_country:
            text = without_country

    text = re.sub(r'[,;/]+', ' ', text)
    return ' '.join(text.split()).strip(' -')


def build_precision_queries(location, place_name, postal_code):
    """
    Builds the ordered structured Nominatim query variants.

    Returns:
        list: Tuples of (variant_name, params) where params is a flat dict of
        Nominatim search parameters. The order is most specific first.
    """
    queries = []

    if place_name and postal_code:
        queries.append(
            ('city_postcode', {'city': place_name, 'postalcode': postal_code})
        )
        queries.append(('name', {'q': place_name}))
        queries.append(('postcode', {'postalcode': postal_code}))
    elif place_name:
        queries.append(('name', {'q': place_name}))
    elif postal_code:
        queries.append(('postcode', {'postalcode': postal_code}))

    full_location = ' '.join((location or '').strip().split())
    already_covered = full_location in {place_name or '', postal_code or ''}
    if full_location and not already_covered:
        queries.append(('full', {'q': full_location}))

    return queries


def _normalize_name(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(text.casefold().split())


def _name_variants(value):
    normalized = _normalize_name(value)
    variants = {normalized}

    without_parentheses = re.sub(r'\s*\([^)]*\)\s*$', '', normalized).strip()
    if without_parentheses:
        variants.add(without_parentheses)

    tokens = without_parentheses.split()
    while tokens and tokens[0] in ADMIN_NAME_PREFIXES:
        tokens.pop(0)
    if tokens:
        variants.add(' '.join(tokens))

    return variants


def _entry_name_matches(entry, place_name):
    if not place_name:
        return False

    place = _normalize_name(place_name)
    if place in _name_variants(entry.get('name', '')):
        return True

    name = _normalize_name(entry.get('name', ''))
    return name.startswith(place + ' ')


def _entry_postcode(entry):
    address = entry.get('address')
    if not isinstance(address, dict):
        return ''
    return str(address.get('postcode', ''))


def postcode_matches(entry, postal_code):
    """Returns True when the entry belongs to the requested postal code."""
    if not postal_code or not isinstance(entry, dict):
        return False
    if _entry_postcode(entry) == str(postal_code):
        return True
    return str(entry.get('name', '')) == str(postal_code)


def candidate_matches_location(entry, place_name=None, postal_code=None):
    """
    Returns False when an entry contradicts both the name and the postal code.

    A missing postal code in the entry is not treated as a contradiction, so
    valid results without address details are still accepted. This rejects
    lookups such as "2490 Balen" returning "Saas-Balen" (postcode 3908).
    """
    if not isinstance(entry, dict):
        return False
    if not place_name or not postal_code:
        return True
    if _entry_name_matches(entry, place_name):
        return True
    if not _entry_postcode(entry):
        return True
    return postcode_matches(entry, postal_code)


def candidate_sort_key(entry, place_name, postal_code):
    """
    Returns a sort key where lower is better.

    Settlement results beat postal code areas when a place name is known. If no
    place name is known, a postal code area is the expected result.
    """
    if not isinstance(entry, dict):
        return (99, 99, 99, 99, 0.0)

    postcode = is_postcode(entry)
    name_match = _entry_name_matches(entry, place_name)
    postcode_match = bool(postal_code) and _entry_postcode(entry) == str(postal_code)

    addresstype = str(entry.get('addresstype') or '')
    entry_type = str(entry.get('type') or '')
    is_city = addresstype in CITY_ADDRESSTYPES or entry_type in CITY_ADDRESSTYPES
    is_area = addresstype in AREA_ADDRESSTYPES or entry_type in AREA_ADDRESSTYPES
    is_village = (
        addresstype in VILLAGE_ADDRESSTYPES or entry_type in VILLAGE_ADDRESSTYPES
    )

    if place_name:
        if is_city:
            tier = 0 if name_match else 1
        elif is_area:
            tier = 2 if name_match else 4
        elif is_village:
            tier = 3 if name_match else 4
        else:
            tier = 5
        if postcode:
            tier = max(tier, 6)
    else:
        if postcode:
            tier = 0
        elif is_city or is_village:
            tier = 1
        elif is_area:
            tier = 2
        else:
            tier = 3

    try:
        place_rank = int(entry.get('place_rank', 99))
    except (TypeError, ValueError):
        place_rank = 99
    try:
        importance = float(entry.get('importance', 0.0))
    except (TypeError, ValueError):
        importance = 0.0

    return (
        tier,
        0 if name_match else 1,
        0 if postcode_match else 1,
        -importance,
        place_rank,
    )


def rank_nominatim_candidates(candidates, place_name, postal_code):
    """
    Selects the best candidate while preserving Nominatim's response order as
    the final tie breaker.
    """
    if not candidates:
        return None

    indexed = enumerate(candidates)
    _, best = min(
        indexed,
        key=lambda item: candidate_sort_key(item[1], place_name, postal_code)
        + (item[0],),
    )
    return best


def candidate_is_good_enough(entry, place_name, postal_code=None):
    """Returns True when a query variant already produced a preferred result."""
    if not candidate_matches_location(entry, place_name, postal_code):
        return False
    if place_name:
        return is_settlement(entry)
    return is_postcode(entry) or is_settlement(entry)


def summarize_candidate(entry, variant, countrycodes):
    """Builds the metadata stored in the debug details file."""
    entry = entry or {}
    address = entry.get('address')
    if not isinstance(address, dict):
        address = {}

    return {
        'query_variant': variant,
        'countrycodes': countrycodes,
        'osm_type': entry.get('osm_type'),
        'osm_id': entry.get('osm_id'),
        'type': entry.get('type'),
        'addresstype': entry.get('addresstype'),
        'name': entry.get('name'),
        'display_name': entry.get('display_name'),
        'place_rank': entry.get('place_rank'),
        'importance': entry.get('importance'),
        'postcode': address.get('postcode'),
        'address': address,
        'boundingbox': entry.get('boundingbox'),
        'radius_classic': calculate_radius_from_bbox_center(entry.get('boundingbox')),
    }


def _radius_number(entry):
    radius = calculate_radius_from_bbox_center((entry or {}).get('boundingbox'))
    if isinstance(radius, (int, float)):
        return float(radius)
    return None


def choose_smaller_area(settlement_entry, postcode_entry):
    """
    Chooses the more precise of a settlement and a postal code area.

    Returns:
        tuple: (chosen entry, selection info dict)
    """
    settlement_radius = _radius_number(settlement_entry)
    postcode_radius = _radius_number(postcode_entry)
    info = {
        'settlement_radius_m': settlement_radius,
        'postcode_radius_m': postcode_radius,
    }

    if postcode_entry is None:
        return settlement_entry, {**info, 'selection': 'only_settlement'}
    if settlement_entry is None:
        return postcode_entry, {**info, 'selection': 'only_postcode'}

    if settlement_radius is not None and postcode_radius is not None:
        if postcode_radius <= settlement_radius:
            return postcode_entry, {**info, 'selection': 'postcode_smaller'}
        return settlement_entry, {**info, 'selection': 'settlement_smaller'}

    if postcode_radius is not None:
        return postcode_entry, {**info, 'selection': 'postcode_radius_only'}
    if settlement_radius is not None:
        return settlement_entry, {**info, 'selection': 'settlement_radius_only'}

    return settlement_entry, {**info, 'selection': 'no_radius'}


def calculate_radius_from_bbox_center(boundingbox):
    """
    Calculates the classic radius from the bounding box center to its north-west
    corner. This keeps comparison values compatible with the historical strategy.

    Returns:
        int or str: Radius in meters, or 'N/A' if the input is incomplete.
    """
    if not boundingbox:
        return 'N/A'

    try:
        south, north, west, east = map(float, boundingbox)
    except (TypeError, ValueError):
        return 'N/A'

    center = ((south + north) / 2, (west + east) / 2)
    return round(geodesic(center, (north, west)).meters)


def precision_rejection(precision_entry, classic_entry, mode='disjoint'):
    """
    Returns guard details when the precision result is rejected.

    mode='old-radius' rejects any marker outside the classic radius circle.
    mode='disjoint' rejects only when the precision and classic areas do not
    overlap, which avoids blocking valid moves away from tiny point baselines.
    """
    if not isinstance(precision_entry, dict) or not isinstance(classic_entry, dict):
        return None

    try:
        precision_point = (
            float(precision_entry.get('lat')),
            float(precision_entry.get('lon')),
        )
        classic_point = (
            float(classic_entry.get('lat')),
            float(classic_entry.get('lon')),
        )
    except (TypeError, ValueError):
        return None

    old_radius = calculate_radius_from_bbox_center(classic_entry.get('boundingbox'))
    if not isinstance(old_radius, (int, float)):
        return None

    precision_radius = calculate_radius_from_bbox_center(
        precision_entry.get('boundingbox')
    )
    if not isinstance(precision_radius, (int, float)):
        precision_radius = 0

    threshold = (
        old_radius
        if mode == 'old-radius'
        else old_radius + precision_radius
    )
    distance = geodesic(precision_point, classic_point).meters
    if distance <= threshold:
        return None

    return {
        'distance_m': round(distance, 1),
        'old_radius_m': old_radius,
        'precision_radius_m': round(precision_radius, 1),
        'threshold_m': round(threshold, 1),
    }


def calculate_radius_from_point(boundingbox, lat, lon):
    """
    Calculates a radius around the selected marker that still contains the whole
    bounding box.

    Returns:
        int or str: Radius in meters, or 'N/A' if the input is incomplete.
    """
    if not boundingbox:
        return 'N/A'

    try:
        south, north, west, east = map(float, boundingbox)
        point = (float(lat), float(lon))
    except (TypeError, ValueError):
        return 'N/A'

    corners = [
        (south, west),
        (south, east),
        (north, west),
        (north, east),
    ]
    return round(max(geodesic(point, corner).meters for corner in corners))
