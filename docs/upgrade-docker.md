# Upgrade der Docker-Installation

- **Ausgangsversion:** Tag `20261022`
- **Zielversion:** Branch `feature/profile-update-date` (nach dem Merge: aktueller Master)

Diese Anleitung beschreibt das Upgrade einer bestehenden Docker-Installation. Die Installation mit `docker compose` wird dabei nicht neu aufgesetzt; Konfiguration, Cache und Karten-Daten bleiben erhalten.

## Was sich ändert

- Die TTL-Bereiche für `user_details` und `nominatim` stehen jetzt in `cache_config.json`.
- Die TTL wird pro Cacheeintrag zufällig gezogen. Das frühere 1-%-Thinning entfällt.
- `--fast` wird weiterhin akzeptiert, hat aber keine Wirkung mehr. Die bestehende Crontab muss nicht geändert werden.
- Jedes Mitglied erhält `profile_updated_at`. Die Karte zeigt im Popup `Stand: TT.MM.JJJJ`; der exakte Zeitstempel steht im Tooltip.
- Alte Cacheeinträge bleiben gültig. Bei `user_details`-Einträgen ohne Zeitstempel wird der Abrufzeitpunkt aus dem bisherigen Ablaufdatum rekonstruiert.
- Die neuen TTLs gelten nur für neu geschriebene Cacheeinträge. Der erste Lauf nach dem Upgrade erzwingt keine vollständige Aktualisierung.
- `utils/clear_nominatim_cache.py` muss für dieses Upgrade **nicht** erneut ausgeführt werden.
- Cron und Web verwenden jetzt denselben Host-Pfad `docker/webserver/www_data/shared`. IDE und native Installation schreiben ebenfalls dorthin; das manuelle Kopieren der Kartendaten entfällt.
- Das Debug-`members.json` wird nach `/app/members.json` geschrieben und nicht mehr über den Web-Root ausgeliefert.

## Vorbereitung

Im Projektverzeichnis auf dem Docker-Host:

```bash
cd /pfad/zu/vmkarte

cp docker-compose.yml docker-compose.yml.bak
cp -a config config.bak
cp -a volumes volumes.bak
[ -d docker/webserver/www_data/shared ] && cp -a docker/webserver/www_data/shared docker/webserver/www_data/shared.bak
```

Die Sicherung von `volumes/` und des bisherigen Shared-Verzeichnisses ist optional, aber empfohlen. Sie enthalten den Cache und die erzeugten Kartendaten.

Neuen Stand auschecken:

```bash
git fetch --all --tags
git checkout feature/profile-update-date
```

Falls der Branch noch nicht lokal vorhanden ist:

```bash
git fetch origin feature/profile-update-date
git checkout feature/profile-update-date
```

## docker-compose.yml anpassen

Die neue Version benötigt einen zusätzlichen Mount für den Cron-Container:

```yaml
  cron:
    # ...
    volumes:
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
      - ./config/config.json:/app/config.json
      - ./config/cache_config.json:/app/cache_config.json:ro
      - ./volumes/cron/cache:/app/cache
      - ./docker/webserver/www_data/shared:/app/shared
```

Neu sind `cache_config.json` und der gemeinsame Shared-Pfad. Der Web-Service verwendet denselben Host-Pfad:

```yaml
  web:
    # ...
    volumes:
      - ./config/.htpasswd:/etc/nginx/.htpasswd
      - ./docker/webserver/www_data/shared:/www_data/shared:ro
```

Bestehende Kartendaten aus `volumes/shared` einmalig übernehmen. Nur `vmforum_members.json` kopieren, nicht das alte Debug-`members.json`:

```bash
mkdir -p docker/webserver/www_data/shared
cp -a volumes/shared/vmforum_members.json docker/webserver/www_data/shared/
```

Danach kann `./volumes/shared` aus der Compose-Datei entfernt werden. Der Cache bleibt unter `./volumes/cron/cache` erhalten.

## cache_config.json anlegen

```bash
cp config/cache_config.json.sample config/cache_config.json
```

Die Datei kann anschließend angepasst werden:

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

Wichtig: Der Mount-Quellpfad muss eine reguläre Datei sein. Fehlt `config/cache_config.json`, kann Docker beim Start ein Verzeichnis an dieser Stelle anlegen. Dann greifen zwar die Default-Werte, die gewünschte externe Konfiguration wird aber nicht gelesen.

Der Build benötigt außerdem `src/data_grabber/cache_config.json` im Build-Kontext. Die Datei ist im Branch enthalten. Änderungen an den TTLs greifen beim nächsten Prozessstart, also beim nächsten Cron-Lauf oder beim manuellen Lauf.

## Container neu bauen und starten

Sowohl der Cron-Container (Python-Code) als auch der Web-Container (`karte.html`) haben sich geändert:

```bash
docker compose build
docker compose up -d
```

Status prüfen:

```bash
docker compose ps
docker compose logs --tail=50 cron
```

## Ersten Lauf manuell auslösen

Der Cronjob läuft regulär um 03:33 Uhr. Für das Upgrade kann der Lauf direkt im Container gestartet werden:

```bash
docker compose exec cron python3 /app/data_grabber.py
```

`--fast` kann weiterhin angegeben werden, ist aber wirkungslos. Der Lauf kann bei leerem Cache mehrere Stunden dauern; mit dem vorhandenen Cache geht er schneller.

## Verifikation

Effektive Cache-Konfiguration prüfen:

```bash
docker compose exec cron python3 -c "from libs.cache_config_lib import CACHE_CONFIG; print(CACHE_CONFIG)"
```

Datenstand in der erzeugten JSON-Datei prüfen:

```bash
grep -m1 profile_updated_at docker/webserver/www_data/shared/vmforum_members.json
```

Anzahl der Einträge mit Zeitstempel:

```bash
docker compose exec cron python3 -c "import json; data=json.load(open('/app/shared/vmforum_members.json', encoding='utf-8')); print(sum(1 for m in data if m.get('profile_updated_at')), '/', len(data))"
```

Karte im Browser mit `Strg+F5` bzw. `Cmd+Shift+R` neu laden. In den Popups muss `Stand: TT.MM.JJJJ` erscheinen. Bei Einträgen ohne Profilabruf steht `Stand: unbekannt`.

## Troubleshooting: „Stand: unbekannt“ bei allen Profilen

Wenn in der JSON-Datei Zeitstempel stehen, die Karte aber überall `Stand: unbekannt` zeigt, lädt der Browser sehr wahrscheinlich eine andere oder ältere JSON-Datei als die geprüfte.

1. Im Browser die Entwicklerwerkzeuge öffnen: `Netzwerk` → `vmforum_members.json` → Antwort ansehen. Enthält die Antwort `profile_updated_at`?
2. Wenn nein, liefert der Webserver eine alte Datei. Im Docker-Betrieb prüfen:
   ```bash
   docker compose exec cron ls -l /app/shared/vmforum_members.json
   docker compose exec web ls -l /www_data/shared/vmforum_members.json
   ```
   Beide Pfade müssen auf dasselbe Host-Verzeichnis `docker/webserver/www_data/shared` zeigen. Wurde der Scraper außerhalb des Containers mit dem neuen Stand ausgeführt, schreibt er standardmäßig ebenfalls dorthin. Prüfen, ob `VMKARTE_SHARED_DIR` auf ein anderes Verzeichnis zeigt. Andernfalls den Lauf im Cron-Container ausführen:

   ```bash
   docker compose exec cron python3 /app/data_grabber.py
   ```
3. Wenn die Antwort `profile_updated_at` enthält, die Karte aber weiterhin `unbekannt` zeigt: Browser-Konsole öffnen. Die Karte gibt dort aus, wie viele Einträge mit Zeitstempel geladen wurden. Bei `0/...` ist die falsche JSON-Datei im Browser; bei einem Wert größer 0 ist die `karte.html` veraltet und muss neu ausgeliefert werden.
4. Die Karte lädt die JSON-Datei mit `cache: 'no-store'`. Zusätzlich hilft ein Hard-Refresh (`Strg+F5` bzw. `Cmd+Shift+R`), um eine alte `karte.html` zu verwerfen.

## Rollback

```bash
git checkout 20261022
docker compose build
docker compose up -d
```

Die zusätzlichen Mounts für `cache_config.json` und `docker/webserver/www_data/shared` können bestehen bleiben; die alte Version ignoriert `cache_config.json` und schreibt weiterhin nach `/app/shared`, also in dasselbe Host-Verzeichnis. Der Cache bleibt kompatibel und muss nicht gelöscht werden. Die alte Version ignoriert auch `profile_updated_at` in der JSON-Ausgabe.

Hinweis: Die alte Version schreibt `members.json` wieder in das Shared-Verzeichnis, also in den Web-Root. Nach dem Rollback sollte diese Datei dort nicht öffentlich erreichbar bleiben.

Falls beim Rollback auch die alte Karte verwendet werden soll, den Web-Container ebenfalls neu bauen (siehe oben).

## Hinweise

- Der erste Lauf aktualisiert nicht automatisch alle Profile. Bestehende Cacheeinträge behalten ihr bisheriges Ablaufdatum. Die Anzeige zeigt zunächst die rekonstruierten alten Abrufdaten; neue Einträge erhalten die zufällige TTL.
- Für einen Test kann die TTL vorübergehend verkürzt werden, z. B. `user_details` 1–2 Tage und `nominatim` 30–60 Tage. Das erhöht die Zahl der Forum- und Nominatim-Abfragen deutlich und ist nicht für den Produktivbetrieb gedacht.
- Ein vollständiges Leeren des Caches (`volumes/cron/cache`) erzwingt einen kompletten Neuaufbau mit ca. 6.900 Profilabrufen und bis zu ca. 3.000 Nominatim-Abfragen. Nur bei Bedarf und möglichst nicht während der Hauptnutzungszeit durchführen.
- `config/config.json` mit den Zugangsdaten bleibt unverändert.
