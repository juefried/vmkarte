# Velomobilforum Mitgliederkarte

Greift Mitgliederdaten über die XenForo-REST-API aus dem velomobilforum.de ab und stellt sie in einer Karte dar.
Weiterführung des Projektes von Christoph Moder.

> **Stand 31.10.2026:** Der HTML-Scraper wurde durch die REST-API ersetzt. Der Betrieb
> nutzt einen User-Key mit `user:read`; Mitgliederliste und `custom_fields` werden
> gelesen. Fahrzeug-Optionswerte werden über `vehicle_label_map.json` und einen
> Best-Guess-Resolver in Anzeigenamen übersetzt. Details stehen in
> `DOKUMENTATION.md`, Abschnitte 17 und 18.

## Installation

```bash
git clone https://github.com/username/my_python_project.git
cd vmkarte
pip install -r requirements.txt
```

## Konfiguration

API-Key und Nominatim-Kontakt stehen in `config.json` (Vorlage: `config.example.json`).
Für Docker wird `config/config.json` verwendet (Vorlage: `config/config.json.sample`).

```json
{
  "email": "email-address-for-nominatim",
  "nominatim_user_agent": "vmkarte/2.0 (+https://github.com/??????/vmkarte)",
  "api": {
    "base_url": "https://www.velomobilforum.de/forum/index.php?api/",
    "api_key": "your-forum-api-key",
    "custom_field_map": {
      "vm": "",
      "lr": "",
      "tr": "",
      "other": ""
    }
  }
}
```

`email` und `nominatim_user_agent` bleiben unverändert erforderlich. `nominatim_user_agent` darf beim Ergänzen des API-Blocks nicht entfallen.

`api_key` wird als `XF-Api-Key` gesendet. Der Key benötigt den Scope `user:read` und
muss die Mitgliederliste sowie Profile sehen dürfen. Für dieses Forum reicht ein
Guest-Key nicht aus: Die Mitgliederliste liefert damit HTTP 403, und `custom_fields`
fehlen. Empfohlen ist ein dedizierter User-Key für ein Lese-/Bot-Konto; ein
Super-User-Key mit `XF-Api-User` ist nur die Ausweichlösung.

`custom_field_map` ist optional. Ohne Eintrag werden die Feld-IDs anhand ihrer
Namen erkannt (z. B. `velomobil`, `liegerad`, `trike`, `sonstige`).

Die TTL-Bereiche der Caches stehen in `cache_config.json`:

```json
{
  "user_details": {
    "ttl_days_min": 7,
    "ttl_days_max": 14
  },
  "nominatim": {
    "ttl_days_min": 180,
    "ttl_days_max": 365,
    "negative_ttl_days": 30
  }
}
```

Fehlende Datei oder fehlende Werte verwenden diese Defaults. Die TTL wird pro Cacheeintrag zufällig gezogen, damit sich die Aktualisierungen über die Zeit verteilen. `negative_ttl_days` cacht „kein Treffer“ für 30 Tage; Exceptions werden nicht gecacht.

## Datenpfade

Der Datengrabber schreibt die Kartendaten standardmäßig nach `docker/webserver/www_data/shared/vmforum_members.json`. IDE und native Installation nutzen damit direkt den Web-Root; ein manuelles Kopieren ist nicht nötig.

Im Docker-Betrieb mounten Cron und Web denselben Host-Pfad nach `/app/shared` bzw. `/www_data/shared`. Für einen separaten Web-Root kann der Pfad mit `VMKARTE_SHARED_DIR` überschrieben werden.

Das Debug-`members.json` wird nur mit `--debug` geschrieben und liegt unter `src/data_grabber/members.json` (Docker: `/app/members.json`); es wird nicht über den Web-Root ausgeliefert. Ohne `--debug` wird eine vorhandene Datei gelöscht. Für den Normalbetrieb ist `--debug` nicht nötig; die Kartenausgabe ist identisch.

## Fahrzeuglabels

Die API liefert für Auswahlfelder nur interne Optionswerte, z. B. `df_xl` statt `DF XL`. `src/data_grabber/libs/vehicle_label_map.json` übersetzt bekannte Werte. Für neue Werte nutzt der Resolver vorhandene Labels, Token-Reihenfolge und gelernte Schreibweisen; unbekannte Werte werden humanisiert.

Fehlende oder unsichere Werte lassen sich aus dem Mitglieder-Cache anzeigen:

```bash
cd src/data_grabber
python utils/vehicle_label_map_report.py
```

Mit `--strict` endet der Report mit Status 1, wenn unbekannte Werte gefunden werden.

### Mappingtabelle aktualisieren

1. Report ausführen:

   ```bash
   cd src/data_grabber
   python utils/vehicle_label_map_report.py
   ```

2. Fehlenden Wert in `libs/vehicle_label_map.json` unter `vm`, `lr` oder `tr` ergänzen. Der Schlüssel ist der API-Rohwert, der Wert der Anzeigename:

   ```json
   {
     "lr": {
       "neues_modell": "Neues Modell"
     }
   }
   ```

3. JSON prüfen und Report streng testen:

   ```bash
   python -c "import json; json.load(open('libs/vehicle_label_map.json', encoding='utf-8'))"
   python utils/vehicle_label_map_report.py --strict
   ```

4. Optional die Tests ausführen:

   ```bash
   python -m unittest discover -s tests -p "test_*.py"
   ```

5. Map-Datei committen. Ein Cache-Löschen ist nicht nötig.

Im Docker-Betrieb ist die Map Teil des Images. Nach einer Änderung daher `docker compose build` und `docker compose up -d` ausführen. Der Report im Container läuft mit:

```bash
docker compose exec cron python3 /app/utils/vehicle_label_map_report.py
```

## Gezielte Aktualisierung

```bash
# Mitgliederliste neu laden, damit neue Benutzer sofort gefunden werden
python data_grabber.py --refresh-members

# Profil und Ort eines Benutzers sofort aktualisieren
python data_grabber.py --refresh-user 12345

# Mehrere Benutzer per UID oder exaktem Forennamen
python data_grabber.py --refresh-user 12345,67890
python data_grabber.py --refresh-user "Max Mustermann"
```

`--refresh-user` umgeht den `user_details`-Cache und fragt Nominatim für dieses Profil ohne Cache-Lesen ab. Das frische Ergebnis wird mit neuer TTL gespeichert. Ist der Benutzer noch nicht im 23-Stunden-Cache der Mitgliederliste, wird diese automatisch einmal neu geladen.

Die Ortsangabe stammt aus der Mitgliederliste. Ohne `--refresh-members` kann sie aus dem 23-Stunden-Cache kommen. Für garantiert frische Ortsdaten beide Optionen kombinieren:

```bash
python data_grabber.py --refresh-members --refresh-user 12345
```

## Lokale Ortsauflösung vergleichen

Die Strategie `precision` ist der Default. Bei `PLZ + Ortsname` vergleicht sie Siedlung und PLZ-Fläche und nimmt die kleinere Fläche (bei Gleichstand die PLZ), damit sowohl Ebersberg als auch Berlin/Hamburg sinnvoll aufgelöst werden. Die bisherige Auflösung bleibt als Opt-out über `--location-strategy classic` verfügbar.

```bash
cd src/data_grabber

# 1. Produktionsnahen Classic-Stand inkl. Debug-Rohdaten erzeugen
python data_grabber.py --debug --location-strategy classic

# 2. members.json + vmforum_members.json als feste Ausgangsbasis einfrieren
python utils/freeze_location_baseline.py

# 3. Vergleichslauf auf derselben Mitgliederbasis
python data_grabber.py --members-from ../../local/baseline/members.json \
  --write-location-details

# 4. Änderungen sortiert ausgeben (.csv, .json oder .md)
python utils/compare_locations.py --output ../../local/compare/locations.csv
```

`members.json` enthält die Adressangaben (Rohdaten), `vmforum_members.json` die daraus ermittelten Koordinaten. Der Report verbindet beide über die UID und sortiert nach Auffälligkeit. Mit `--write-location-details` schreibt der Precision-Lauf zusätzlich `location-details.json`; darin steht, welches OSM-Objekt gewählt wurde (`type`, `addresstype`, `display_name`). In Produktion wird diese Datei nicht geschrieben.

Der Report markiert zwei Signale:

- `outside_old_radius`: Der neue Marker liegt außerhalb des alten Radius-Kreises.
- `areas_disjoint`: Alter und neuer Kreis überschneiden sich nicht.
- `radius_grew` / `radius_shrank`: Der neue Radius ist größer bzw. kleiner als der alte.
- `precision_rejected`: Der Precision-Kandidat wurde vom Guard verworfen, der Classic-Standort bleibt erhalten.

`--focus improvements` (Alias `radius-shrank`) zeigt gezielt die Verbesserungen: kleinerer Radius und nicht außerhalb des alten Radius. `--focus rejected` zeigt die vom Guard verworfenen Precision-Kandidaten.

Der Guard ist standardmäßig `disjoint`: Er verwirft nur, wenn sich alter und neuer Bereich gar nicht überschneiden. `--precision-guard old-radius` ist strenger, `none` deaktiviert ihn beim Geocoding-Lauf.

Ortsnamen-Korrekturen liegen in `libs/country_mapping.json` und in `prepare_location()` (`libs/location_mapping_rules_lib.py`), z. B. `Stockholm` → Schweden, `Franken` → Bayern, `South Florida` → Florida.

Für den Radius wird standardmäßig der **klassisch abgeleitete Radius des neuen OSM-Objekts** mit dem alten Radius verglichen (`radius_basis=derived`). Damit erzeugt die geänderte Radiusformel keine Fehlalarme. Ist der klassische Radius nicht ableitbar, wird der Karten-Radius verwendet (`radius_basis=map`); der Report weist die Basis pro Zeile aus.

Wichtige Optionen:

```bash
# Nur Auffälligkeiten (Default), alle Änderungen oder gezielte Signale
python utils/compare_locations.py --focus suspicious
python utils/compare_locations.py --all
python utils/compare_locations.py --focus outside-old-radius
python utils/compare_locations.py --focus radius-grew
python utils/compare_locations.py --focus improvements  # nur Radius-Verbesserungen
python utils/compare_locations.py --focus rejected      # vom Guard verworfen

# Einzelnen Benutzer detailliert anzeigen (UID oder exakter Name)
python utils/compare_locations.py --user JohnDoe
python utils/compare_locations.py --user 11538
# Zeigt eine bereinigte Objektbezeichnung, OSM-ID und die rohe Nominatim-Adresse.
# Das irreführende Adressfeld "municipality" (z. B. Ebersberg/Baiern) wird nicht
# in die Kurzbezeichnung übernommen.

# Schwellen für Radius-Wachstum
python utils/compare_locations.py --min-radius-growth-m 500 --min-radius-growth-pct 20

# Radius-Basis erzwingen
python utils/compare_locations.py --radius-basis map
```

`--output` schreibt immer alle Änderungen inklusive Flags (`--focus` filtert nur die Konsolenausgabe).

Precision-Abfragen nutzen den getrennten Cache-Namespace `precision-v1`; ein alter Classic-Treffer kann sie nicht bedienen. Mit `--refresh-locations` werden alle Nominatim-Abfragen frisch ausgeführt.

`local/baseline/` und `src/data_grabber/location-details.json` enthalten personenbezogene Daten und sind gitignoriert.

## Release 3.0 (Branch `release/3.0-pwa`)

- [Auth-Service und formularbasierte Anmeldung](docs/upgrade-3.0-auth.md)
- [OAuth2-Anmeldung über das Velomobil-Forum](docs/upgrade-3.0-oauth.md)
- Datenstatus aus dem Datengrabber (`shared/data-status.json`)
- Frontend-Datenloader mit IndexedDB, lokalem Start, ETag-Abgleich und manuellem Refresh
- Dauerhafte, dezente Statusanzeige mit Quelle `Server`/`lokal` und Offline-Badge
- Service Worker mit App-Shell-Cache, Offline-Reload und kontrolliertem Update-Hinweis
- PWA-Manifest, Icons und Installierbarkeit

Dieser Stand ersetzt HTTP Basic Authentication durch einen Go-Auth-Service und
nginx `auth_request`. Standortfunktion und Domainumzug folgen in Phase 8 und 10.

## Upgrade von der Version 20261022

- [Docker-Installation](docs/upgrade-docker.md)
- [Native Server-Installation](docs/upgrade-native.md)
