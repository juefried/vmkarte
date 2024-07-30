import json
import re

with open('libs/country_mapping.json', 'r', encoding='utf-8') as f:
    country_mapping = json.load(f)
    # Lowercase the country codes and their location names
    country_mapping = {k.lower(): [loc.lower() for loc in v] for k, v in country_mapping.items()}
    f.close()

# Erzeuge eine neue Struktur mit umgekehrten Schlüssel-Wert-Paaren
country_mapping_reverse = {}
for code, names in country_mapping.items():
    # Ländercode als Schlüssel hinzufügen
    country_mapping_reverse[code.lower()] = code

    # Namen der Städte/Länder hinzufügen
    for name in names:
        country_mapping_reverse[name.lower()] = code

# Sortiere die neuen Schlüssel nach der Länge, längere zuerst
country_mapping_reverse = dict(
    sorted(country_mapping_reverse.items(), key=lambda item: len(item[0]), reverse=True)
)

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

    while True:
        new_location = re.sub(r'^(bei|nähe|nahe|von|in|im) +', '', location)
        if new_location == location:
            break
        location = new_location

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
    location = location.replace("/main", "am main")
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
    location = re.sub(r'\bkreis\b(?=\s+[a-zäöüß\-]+)', 'landkreis', location)
    location = re.sub(r'\b((groß)?raum|umland)\b(?=\s+[a-zäöüß\-]+)', '', location)
    location = location.replace("landkreis plön, sh", "kreis plön")
    location = location.replace("landkreis waf", "kreis warendorf")

    match = re.match(r'^(\d{5})(\s+bei)?\s+([a-zäöüß]{1,3})$', location)
    if match:
        plz, bei, code = match.groups()
        if code in kuerzel_mapping:
            location = f"{plz} {kuerzel_mapping[code]}".lower()
    if len(location) >= 1 and len(location) <= 3 and location.isalpha() and location in kuerzel_mapping:
        location = kuerzel_mapping.get(location, location)

    location = location.replace("(15 km no von stuttgart)", "")
    location = location.replace("01099 - doppel-d", "dresden")

    if re.match(r'^(hier|an der isar|norden|nichts|süden|104x|zentral|tor zur welt|süd-?westen|bird mountains)$', location):
        return None

    if location.isdigit() and len(location) <= 3:
        return None

    location = ' '.join(location.strip().split())
    return location


def analyze_location_for_country(location):
    location = location.lower()

    # Entferne alle Sonderzeichen außer Buchstaben, Zahlen und Leerzeichen
    location = re.sub(r'[^\w\s-]', '', location)

    # Finde country-code mit Postleitzahl
    match = re.match(r'^([a-z]{1,3})[ -](\d{4,5})', location)
    if match:
        country_code = get_country_code(match.group(1), country_mapping)
        if country_code is not None:
            return country_code

    for name, code in country_mapping_reverse.items():
        # Erstelle einen regulären Ausdruck, der sicherstellt, dass der gesuchte Name von Wortgrenzen umgeben ist
        pattern = r'\b' + re.escape(name) + r'\b'
        if re.search(pattern, location):
            return code

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
