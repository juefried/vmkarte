import json
import re

with open('libs/country_mapping.json', 'r', encoding='utf-8') as f:
    country_mapping = json.load(f)
    # Lowercase the country codes and their location names
    country_mapping = {k.lower(): [loc.lower() for loc in v] for k, v in country_mapping.items()}
    f.close()

# Create a new structure with reversed key-value pairs
country_mapping_reverse = {}
code: object
for code, names in country_mapping.items():
    # Add country code as a key
    country_mapping_reverse[code.lower()] = code.translate(str.maketrans('', '', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))

    # Translate city/country names to lowercase
    for name in names:
        country_mapping_reverse[name.lower()] = code.translate(str.maketrans('', '', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
        country_mapping_reverse[name.lower()] = code

# Sortiere die neuen Schlüssel nach der Länge, längere zuerst
country_mapping_reverse = dict(
    sorted(country_mapping_reverse.items(), key=lambda item: len(item[0]), reverse=True)
)

with open('libs/kuerzel_mapping.json', 'r', encoding='utf-8') as f:
    kuerzel_mapping = json.load(f)
    kuerzel_mapping = {k.lower(): v.lower() for k, v in kuerzel_mapping.items()}
    f.close()


def get_country_code(country_name: str, country_mapping: dict) -> str:
    """
    Returns the country code associated with a given country name.

    Args:
        country_name (str): The name of the country.
        country_mapping (dict): A dictionary mapping country names to their codes.

    Returns:
        str: The country code associated with the given country name.
              Returns None if the country name is not found.
    """
    # Convert the country name to lowercase
    country_name = country_name.lower()

    # Iterate over the country mapping dictionary
    for country_code, names in country_mapping.items():
        # Check if the country name is in the list of names
        if country_name in names:
            # Return the country code if found
            return country_code

    # Return None if the country name is not found
    return None


def prepare_location(location: str) -> str:
    """
    Cleans and standardizes the given location string.
    Args:
        location (str): The location string to be cleaned and standardized.
    Returns:
        str: The cleaned and standardized location string.
    Raises:
        None
    """

    # Remove leading and trailing whitespace and convert to lowercase
    location = ' '.join(location.strip().split()).lower()

    # Remove leading words like 'bei', 'nähe', 'von', etc.
    while True:
        new_location = re.sub(r'^(bei|nähe|nahe|von|in|im|der) +', '', location)
        if new_location == location:
            break
        location = new_location

    # Replace specific substrings with their standardized versions
    location = location.replace("(centro storico)", "")
    location = location.replace("black forest", "schwarzwald")
    location = location.replace("s-h", "schleswig-holstein")
    location = location.replace("b. münchen", "")
    location = location.replace("südhessen", "hessen")
    location = location.replace("nordhessen", "hessen")
    location = location.replace("ostbayern", "bayern")
    location = location.replace("in niederösterreich", "österreich")
    location = location.replace("süd brandenburg", "brandenburg")
    location = location.replace("unter- mittelfranken", "mittelfranken")
    location = location.replace("/ hunsrück", "")
    location = location.replace("/main", " am main")
    location = location.replace("86399 landkreis augsburg", "86399 bobingen")
    location = location.replace("leipziger land", "")
    location = location.replace("n.r.w", "nrw")
    location = location.replace("st.vith", "Sankt Vith, Belgien")
    location = location.replace("nürtingen a. n.", "nürtingen")
    location = location.replace("schwabenländle", "baden würtemberg")
    location = location.replace("ruhrhalbinsel", "überruhr")
    location = location.replace("umgebung", "")
    location = location.replace("südlicher wienerwald", "wienerwald, austria")
    location = location.replace("markgräfler land", "markgräflerland")
    location = location.replace("stuttgart-vaihingen", "vaihingen")
    location = location.replace("40000 germany", "düssedorf")
    location = location.replace("in obb", "in oberbayern")
    location = location.replace("79***", "schwarzwald")
    location = location.replace("75... enzkreis", "enzkreis")

    # Replace 'kreis' with 'landkreis' if followed by a lowercase word
    location = re.sub(r'\bkreis\b(?=\s+[a-zäöüß\-]+)', 'landkreis', location)

    # Remove 'großraum' and 'umland' if followed by a lowercase word
    location = re.sub(r'\b((groß)?raum|umland)\b(?=\s+[a-zäöüß\-]+)', '', location)

    # Replace specific substrings with their standardized versions
    location = location.replace("landkreis plön, sh", "kreis plön")
    location = location.replace("landkreis waf", "kreis warendorf")
    location = location.replace("(15 km no von stuttgart)", "")
    location = location.replace("01099 - doppel-d", "dresden")

    # Remove 'bei' followed by a word
    location = re.sub(r'\bbei\b [\wäöüß\-]+', '', location)

    # Check if the location string is in the format of a postal code followed by an
    # optional 'bei' and a country code. If it is, replace the postal code and country
    # code with the standardized version from the `kuerzel_mapping` dictionary.
    match = re.match(r'^(\d{5})(\s+bei)?\s+([a-zäöüß]{1,3})$', location)
    if match:
        plz, bei, code = match.groups()
        if code in kuerzel_mapping:
            location = f"{plz} {kuerzel_mapping[code]}".lower()

    # Check if the location string is a three-letter country code and if it is in the
    # `kuerzel_mapping` dictionary. If it is, replace the country code with the
    # standardized version from the `kuerzel_mapping` dictionary.
    if len(location) >= 1 and len(location) <= 3 and location.isalpha() and location in kuerzel_mapping:
        location = kuerzel_mapping.get(location, location)

    # Check if the location string matches any of the listed patterns and if so, return
    # `None`.
    if re.match(r'^(hier|an der isar|norden|nichts|süden|104x|zentral|tor zur welt|süd-?westen|bird mountains)$', location):
        return None

    # Check if the location string is a digit and less than or equal to 3 characters long.
    # If it is, return `None`.
    if location.isdigit() and len(location) <= 3:
        return None

    # Remove leading and trailing whitespace and replace consecutive whitespace with
    # a single space.
    location = ' '.join(location.strip().split())
    return location


def analyze_location_for_country(location: str) -> str:
    """
    Analyzes a location string to determine the country code.

    Args:
        location (str): The location string to analyze.

    Returns:
        str: The country code if found, otherwise None.
    """
    if location is None:
        return None

    # Convert location to lowercase
    location = location.lower()

    # Remove all special characters except letters, numbers, and spaces
    location = re.sub(r'[^\w\s-]', '', location)

    # Find country code with postal code
    match = re.match(r'^([a-z]{1,3})[ -](\d{4,5})', location)
    if match:
        country_code = get_country_code(match.group(1), country_mapping)
        if country_code is not None:
            return country_code

    # Check for country name in location
    for name, code in country_mapping_reverse.items():

        # Create a regular expression pattern that ensures the searched name is surrounded by word boundaries
        pattern = r'\b' + re.escape(name) + r'\b'
        if re.search(pattern, location):
            return code

    return None


def analyze_location_for_postal_code(location: str) -> str:
    """
    Analyzes a location string to find a valid postal code.

    Args:
        location (str): The location string to analyze.

    Returns:
        str: The postal code if found, None otherwise.
    """
    # Convert location to lowercase
    location = location.lower()

    # Split location into words
    words = re.findall(r'\w+', location, re.UNICODE)

    # Iterate over words and check if they match a valid postal code pattern
    for word in words:
        match = re.match(r'^[0-9]{4,5}$', word)
        if match:
            return word

    # Return None if no valid postal code is found
    return None
