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

## Upgrade von der Version 20261022

- [Docker-Installation](docs/upgrade-docker.md)
- [Native Server-Installation](docs/upgrade-native.md)
