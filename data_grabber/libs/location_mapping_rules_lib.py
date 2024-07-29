import json
import re

with open('libs/country_mapping.json', 'r', encoding='utf-8') as f:
    country_mapping = json.load(f)
    # Lowercase the country codes and their location names
    country_mapping = {k.lower(): [loc.lower() for loc in v] for k, v in country_mapping.items()}
    f.close()

with open('libs/kuerzel_mapping.json', 'r', encoding='utf-8') as f:
    kuerzel_mapping = json.load(f)
    kuerzel_mapping = {k.lower(): v.lower() for k, v in kuerzel_mapping.items()}
    f.close()

def get_country_code(country_name, country_mapping):
    country_name = country_name.lower()
    for country_code, names in country_mapping.items():
        if country_name in names:
            return country_code
    return None

def prepare_location(location):
    location = ' '.join(location.strip().split())
    location = location.lower()

    if location.startswith("bei "):
        location = location[len("bei "):]
    location = location.replace("(centro storico)", "")
    location = location.replace("s-h", "schleswig-holstein")
    location = location.replace("ottenhofen b. münchen", "ottenhofen")
    location = location.replace("86399 landkreis augsburg", "86399 bobingen")
    location = re.sub(r'\bkreis\b(?=\s+[a-zäöüß\-]+)', 'landkreis', location)
    location = re.sub(r'\b((groß)?raum|umland)\b(?=\s+[a-zäöüß\-]+)', '', location)

    match = re.match(r'^(\d{5})(\s+bei)?\s+([a-zäöüß]{1,3})$', location)
    if match:
        plz, bei, code = match.groups()
        if code in kuerzel_mapping:
            location = f"{plz} {kuerzel_mapping[code]}".lower()
    if len(location) >= 1 and len(location) <= 3 and location.isalpha() and location in kuerzel_mapping:
        location = kuerzel_mapping.get(location, location)

    location = location.replace("(15 km no von stuttgart)", "")
    location = location.replace("01099 - doppel-d", "dresden")

    location = ' '.join(location.strip().split())
    return location

def analyze_location_for_country(location):
    location = location.lower()

    # find country-code with postal code
    # ^{A-Za-z}{1,3}[ -][a-z]{3,50}
    match = re.match(r'^([A-Za-z]{1,3})[ -](\d{4,5})', location)
    if match:
        country_code = get_country_code(match.group(1), country_mapping)
        if country_code is not None:
            return country_code

    words = re.findall(r'\w+', location, re.UNICODE)
    for word in words:
        if len(word) > 1:
            country_code = get_country_code(word, country_mapping)
            if country_code is not None:
                return country_code

    for word in words:
        match = re.match(r'^[0-9]{5}$', word)
        if match:
            return get_country_code("Deutschland", country_mapping)

    if len(words) == 0:
        return None

    # Wenn erster Wert eine PLZ ist, aber keine fünf Zeichen hat
    match = re.match(r'^[0-9]{4,5}$', words[0])
    if match and len(words[0]) != 5:
        return None

    return None


def analyze_location_for_postal_code(location):
    location = location.lower()
    postal_code = None

    words = re.findall(r'\w+', location, re.UNICODE)
    for word in words:
        match = re.match(r'^[0-9]{4,5}$', word)
        if match:
            return word

    return None
