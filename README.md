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
    "ttl_days_max": 365
  }
}
```

Fehlende Datei oder fehlende Werte verwenden diese Defaults. Die TTL wird pro Cacheeintrag zufällig gezogen, damit sich die Aktualisierungen über die Zeit verteilen.

## Datenpfade

Der Scraper schreibt die Kartendaten standardmäßig nach `docker/webserver/www_data/shared/vmforum_members.json`. IDE und native Installation nutzen damit direkt den Web-Root; ein manuelles Kopieren ist nicht nötig.

Im Docker-Betrieb mounten Cron und Web denselben Host-Pfad nach `/app/shared` bzw. `/www_data/shared`. Für einen separaten Web-Root kann der Pfad mit `VMKARTE_SHARED_DIR` überschrieben werden.

Das Debug-`members.json` liegt unter `src/data_grabber/members.json` (Docker: `/app/members.json`) und wird nicht über den Web-Root ausgeliefert.

## Upgrade von der Version 20261022

- [Docker-Installation](docs/upgrade-docker.md)
- [Native Server-Installation](docs/upgrade-native.md)
