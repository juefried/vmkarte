# Velomobilforum Mitgliederkarte

Greift Mitgliederdaten aus dem velomobilforum.de ab und stellt sie in einer Karte dar.
Weiterführung des Projektes von Christoph Moder.

## Installation

```bash
git clone https://github.com/username/my_python_project.git
cd generate_data
pip install -r requirements.txt
```

## Konfiguration

Zugangsdaten und Nominatim-Kontakt stehen in `config.json` (Vorlage: `config.example.json`).

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

Der Scraper schreibt die Kartendaten standardmäßig nach `docker/webserver/www_data/shared/vmforum_members.json`. IDE und native Installation nutzen damit direkt den Web-Root; ein manuelles Kopieren ist nicht nötig.

Im Docker-Betrieb mounten Cron und Web denselben Host-Pfad nach `/app/shared` bzw. `/www_data/shared`. Für einen separaten Web-Root kann der Pfad mit `VMKARTE_SHARED_DIR` überschrieben werden.

Das Debug-`members.json` wird nur mit `--debug` geschrieben und liegt unter `src/data_grabber/members.json` (Docker: `/app/members.json`); es wird nicht über den Web-Root ausgeliefert. Ohne `--debug` wird eine vorhandene Datei gelöscht.

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
