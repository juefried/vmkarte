# Upgrade der nativen Server-Installation

- **Ausgangsversion:** Tag `20261022`
- **Zielversion:** Branch `feature/profile-update-date` (nach dem Merge: aktueller Master)

Diese Anleitung beschreibt das Upgrade einer Installation, bei der der Datengrabber direkt auf dem Server läuft (Cron oder systemd) und der Webserver die Karte als statische Dateien ausliefert.

## Was sich ändert

- Die TTL-Bereiche für `user_details` und `nominatim` stehen jetzt in `cache_config.json`.
- Die TTL wird pro Cacheeintrag zufällig gezogen. Das frühere 1-%-Thinning entfällt.
- `--fast` wird weiterhin akzeptiert, hat aber keine Wirkung mehr. Die bestehende Cron- oder systemd-Konfiguration muss nicht geändert werden.
- Jedes Mitglied erhält `profile_updated_at`. Die Karte zeigt im Popup `Stand: TT.MM.JJJJ`; der exakte Zeitstempel steht im Tooltip.
- Alte Cacheeinträge bleiben gültig. Bei `user_details`-Einträgen ohne Zeitstempel wird der Abrufzeitpunkt aus dem bisherigen Ablaufdatum rekonstruiert.
- Die neuen TTLs gelten nur für neu geschriebene Cacheeinträge. Der erste Lauf nach dem Upgrade erzwingt keine vollständige Aktualisierung.
- Erfolgreiche Nominatim-Abfragen ohne Treffer werden 30 Tage negativ gecacht (`negative_ttl_days` in `cache_config.json`). Exceptions werden weiterhin nicht gecacht.
- `utils/clear_nominatim_cache.py` muss für dieses Upgrade **nicht** erneut ausgeführt werden.
- `utils/cache.py` wurde entfernt.
- Es werden keine neuen Python-Pakete benötigt; `requirements.txt` bleibt unverändert.
- Alle Laufzeitpfade werden script-relativ aufgelöst. Die Kartendaten gehen standardmäßig nach `<repo>/docker/webserver/www_data/shared`; für einen separaten Web-Root kann `VMKARTE_SHARED_DIR` gesetzt werden.
- Das Debug-`members.json` wird nur mit `--debug` nach `src/data_grabber/members.json` geschrieben. Ohne `--debug` wird die Datei nicht erzeugt; vorhandene Kopien am aktuellen Pfad sowie in alten Shared-Verzeichnissen werden beim nächsten Lauf gelöscht.

## Vorbereitung

Im Projektverzeichnis auf dem Server:

```bash
cd /pfad/zu/vmkarte

cp -a src/data_grabber/config.json src/data_grabber/config.json.bak
cp -a src/data_grabber/cache src/data_grabber/cache.bak
[ -d src/data_grabber/shared ] && cp -a src/data_grabber/shared src/data_grabber/shared.bak
[ -d docker/webserver/www_data/shared ] && cp -a docker/webserver/www_data/shared docker/webserver/www_data/shared.bak
```

Die Sicherung von `cache/` und der Shared-Verzeichnisse ist optional, aber empfohlen. `config.json` enthält die Zugangsdaten und sollte in jedem Fall gesichert werden.

Falls die eingecheckte `src/data_grabber/cache_config.json` lokal angepasst wurde, diese Änderung vor dem Branchwechsel sichern:

```bash
cp src/data_grabber/cache_config.json /tmp/cache_config.json.local
```

## Code aktualisieren

```bash
git fetch --all --tags
git checkout feature/profile-update-date
```

Falls der Branch noch nicht lokal vorhanden ist:

```bash
git fetch origin feature/profile-update-date
git checkout feature/profile-update-date
```

Bei einer Installation ohne Git-Checkout müssen mindestens folgende Dateien übernommen werden:

- `src/data_grabber/data_grabber.py`
- `src/data_grabber/cache_config.json`
- `src/data_grabber/libs/` (insbesondere `cache_config_lib.py`, `paths_lib.py`, `data_scraper_lib.py`, `location_nominatim_lib.py`)
- `docker/webserver/www_data/karte.html`

`src/data_grabber/libs/cache_thinning_lib.py` wird nicht mehr verwendet und kann entfernt werden. Das Weglassen ist unschädlich.

## cache_config.json prüfen

Die Datei ist im Repository enthalten und muss im selben Verzeichnis wie `data_grabber.py` liegen:

```text
src/data_grabber/cache_config.json
```

Falls du die Datei vor dem Branchwechsel gesichert hast, die lokale Anpassung jetzt wiederherstellen:

```bash
cp /tmp/cache_config.json.local src/data_grabber/cache_config.json
```

Falls die Datei in einer nicht versionierten Installation fehlt, aus dem neuen Stand übernehmen:

```bash
cp /pfad/zum/neuen/stand/src/data_grabber/cache_config.json src/data_grabber/cache_config.json
```

Alternativ kann sie mit den Default-Werten neu angelegt werden. Die Default-Werte sind:

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

Fehlt die Datei oder ein Wert, greifen diese Defaults. Ungültige Werte brechen den Lauf mit einer klaren Fehlermeldung ab. Änderungen an den TTLs greifen beim nächsten Prozessstart, also beim nächsten Cron-/systemd-Lauf oder beim manuellen Lauf.

## Datengrabber starten

Die bestehende Cron- oder systemd-Konfiguration bleibt unverändert. Für einen manuellen Testlauf:

```bash
cd /pfad/zu/vmkarte/src/data_grabber
/pfad/zu/venv/bin/python data_grabber.py
```

Das Arbeitsverzeichnis ist beliebig: `config.json`, `cache_config.json`, Cache und Ausgabe werden script-relativ aufgelöst. Der Aufruf aus `src/data_grabber` bleibt der einfachste Weg.

Der Aufruf mit `--fast` ist weiterhin möglich, hat aber keine Wirkung mehr:

```bash
/pfad/zu/venv/bin/python data_grabber.py --fast
```

Für Debugging kann `--debug` ergänzt werden. Die Rohdaten landen dann unter `src/data_grabber/members.json`, nicht im Web-Root:

```bash
/pfad/zu/venv/bin/python data_grabber.py --debug
```

Der Lauf kann bei leerem Cache mehrere Stunden dauern. Mit dem vorhandenen Cache geht er schneller. Die Ausgabe erfolgt nach `src/data_grabber/members.json` (Debug) und `docker/webserver/www_data/shared/vmforum_members.json` (Karte). Mit gesetztem `VMKARTE_SHARED_DIR` geht die Kartenausgabe in das dort angegebene Verzeichnis.

## Frontend aktualisieren

Die Karte benötigt die neue `karte.html`. Wenn der Webserver direkt `docker/webserver/www_data/` ausliefert, ist mit dem Code-Update nichts weiter zu tun: Der Scraper schreibt die Kartendaten direkt nach `docker/webserver/www_data/shared/`.

Wenn der Webserver ein separates Web-Root verwendet, die Datei dorthin kopieren und den Datenpfad per Umgebungsvariable setzen:

```bash
cp docker/webserver/www_data/karte.html /var/www/vmforum-karte/karte.html
export VMKARTE_SHARED_DIR=/var/www/vmforum-karte/shared
```

Die Variable muss in der Umgebung des Cron-/systemd-Laufs gesetzt sein. Beispiele:

```cron
VMKARTE_SHARED_DIR=/var/www/vmforum-karte/shared
33 3 * * * cd /pfad/zu/vmkarte/src/data_grabber && /pfad/zu/venv/bin/python data_grabber.py
```

```ini
[Service]
Environment=VMKARTE_SHARED_DIR=/var/www/vmforum-karte/shared
```

Alternativ kann `/var/www/vmforum-karte/shared` ein Symlink auf `/pfad/zu/vmkarte/docker/webserver/www_data/shared` sein.

Weitere statische Dateien (Leaflet, MarkerCluster) haben sich nicht geändert. Die Karte lädt `shared/vmforum_members.json` relativ zu `karte.html`; dieses Verzeichnis muss im Web-Root vorhanden und lesbar sein.

## Verifikation

Effektive Cache-Konfiguration prüfen:

```bash
cd /pfad/zu/vmkarte/src/data_grabber
/pfad/zu/venv/bin/python -c "from libs.cache_config_lib import CACHE_CONFIG, get_ttl_seconds; print(CACHE_CONFIG); print(get_ttl_seconds('user_details'), get_ttl_seconds('nominatim'))"
```

Datenstand in der erzeugten JSON-Datei prüfen:

```bash
cd /pfad/zu/vmkarte/src/data_grabber
grep -m1 profile_updated_at "$(/pfad/zu/venv/bin/python -c 'from libs.paths_lib import VMFORUM_MEMBERS_JSON_PATH; print(VMFORUM_MEMBERS_JSON_PATH)')"
```

Anzahl der Einträge mit Zeitstempel:

```bash
cd /pfad/zu/vmkarte/src/data_grabber
/pfad/zu/venv/bin/python -c "import json; from libs.paths_lib import VMFORUM_MEMBERS_JSON_PATH as p; data=json.load(open(p, encoding='utf-8')); print(sum(1 for m in data if m.get('profile_updated_at')), '/', len(data))"
```

Karte im Browser mit `Strg+F5` bzw. `Cmd+Shift+R` neu laden. In den Popups muss `Stand: TT.MM.JJJJ` erscheinen. Bei Einträgen ohne Profilabruf steht `Stand: unbekannt`.

## Troubleshooting: „Stand: unbekannt“ bei allen Profilen

Wenn in der Scraper-Ausgabe Zeitstempel stehen, die Karte aber überall `Stand: unbekannt` zeigt, liefert der Webserver sehr wahrscheinlich eine andere oder ältere JSON-Datei aus.

1. Im Browser die Entwicklerwerkzeuge öffnen: `Netzwerk` → `vmforum_members.json` → Antwort ansehen. Enthält die Antwort `profile_updated_at`?
2. Wenn nein, die vom Webserver ausgelieferte Datei prüfen:
   ```bash
   grep -m1 profile_updated_at /var/www/vmforum-karte/shared/vmforum_members.json
   ```
   Pfad entsprechend dem eigenen Web-Root anpassen. Fehlt das Feld, prüfen, ob `VMKARTE_SHARED_DIR` im Cron-/systemd-Lauf gesetzt ist. Standardmäßig schreibt der Scraper nach `docker/webserver/www_data/shared`. Für einen separaten Web-Root entweder die Variable setzen oder einen Symlink anlegen:
   ```bash
   ln -sf /pfad/zu/vmkarte/docker/webserver/www_data/shared/vmforum_members.json /var/www/vmforum-karte/shared/vmforum_members.json
   ```
3. Wenn die Antwort `profile_updated_at` enthält, die Karte aber weiterhin `unbekannt` zeigt: Browser-Konsole öffnen. Die Karte gibt dort aus, wie viele Einträge mit Zeitstempel geladen wurden. Bei `0/...` ist die falsche JSON-Datei im Browser; bei einem Wert größer 0 ist die `karte.html` veraltet und muss neu ausgeliefert werden.
4. Die Karte lädt die JSON-Datei mit `cache: 'no-store'`. Zusätzlich hilft ein Hard-Refresh (`Strg+F5` bzw. `Cmd+Shift+R`), um eine alte `karte.html` zu verwerfen.

## Rollback

```bash
cd /pfad/zu/vmkarte
```

Falls `cache_config.json` lokal angepasst wurde, die Änderung vorher sichern und die Arbeitskopie zurücksetzen:

```bash
cp src/data_grabber/cache_config.json /tmp/cache_config.json.local
git checkout -- src/data_grabber/cache_config.json
git checkout 20261022
```

Danach den Cronjob bzw. den systemd-Timer wie gewohnt weiterlaufen lassen. Der Cache bleibt kompatibel und muss nicht gelöscht werden. Die alte Version benötigt `cache_config.json` nicht; beim Checkout wird die versionierte Datei aus dem Arbeitsverzeichnis entfernt. `profile_updated_at` wird von der alten Ausgabe ignoriert.

Achtung: Die alte Version schreibt wieder nach `src/data_grabber/shared` (bzw. in das `shared`-Verzeichnis relativ zum Arbeitsverzeichnis) und legt `members.json` wieder dort ab. Falls der Webserver auf `docker/webserver/www_data/shared` zeigt, muss die alte Ausgabe dorthin kopiert oder die Web-Root-Konfiguration angepasst werden. Die neue `members.json`-Ablage außerhalb des Web-Roots entfällt beim Rollback.

Falls das Frontend bereits aktualisiert wurde, auch die alte `karte.html` wieder ausrollen. Andernfalls zeigt die neue Karte mit den alten Daten überall `Stand: unbekannt`.

## Hinweise

- Das alte `src/data_grabber/shared/` und die alte `src/data_grabber/vmforum_members.json` werden nicht mehr beschrieben und können nach der Umstellung entfernt werden.
- Alte Debug-Dateien im Web-Root entfernen: `rm -f src/data_grabber/shared/members.json /var/www/vmforum-karte/shared/members.json`. Der nächste Lauf ohne `--debug` entfernt die bekannten Pfade ebenfalls automatisch.
- Der erste Lauf aktualisiert nicht automatisch alle Profile. Bestehende Cacheeinträge behalten ihr bisheriges Ablaufdatum. Die Anzeige zeigt zunächst die rekonstruierten alten Abrufdaten; neue Einträge erhalten die zufällige TTL.
- Für einen Test kann die TTL vorübergehend verkürzt werden, z. B. `user_details` 1–2 Tage und `nominatim` 30–60 Tage. Das erhöht die Zahl der Forum- und Nominatim-Abfragen deutlich und ist nicht für den Produktivbetrieb gedacht.
- Ein vollständiges Leeren des Caches (`src/data_grabber/cache/`) erzwingt einen kompletten Neuaufbau mit ca. 6.900 Profilabrufen und bis zu ca. 3.000 Nominatim-Abfragen. Nur bei Bedarf und möglichst nicht während der Hauptnutzungszeit durchführen.
- Nach einem Code-Update die Dateirechte prüfen: Der Cron-/systemd-Benutzer muss `src/data_grabber/cache/` und das Karten-Ausgabeverzeichnis (`docker/webserver/www_data/shared` oder `VMKARTE_SHARED_DIR`) beschreiben können; der Webserver muss `shared/vmforum_members.json` lesen können.
- `src/data_grabber/config.json` mit den Zugangsdaten bleibt unverändert.
