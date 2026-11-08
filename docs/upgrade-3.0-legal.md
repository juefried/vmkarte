# Release 3.0 – Impressum und Datenschutz

**Stand:** 08.11.2026
**Branch:** `feature/legal-pages`

Diese Anleitung beschreibt das Einbinden von Impressum und Datenschutzerklärung
in den Auth-Service sowie die Verlinkung auf Loginseite, Karte und Offline-Seite.

## Überblick

- Impressum und Datenschutzerklärung werden vom Auth-Service gerendert.
- Die persönlichen Betreiberdaten liegen ausschließlich in
  `config/impressum.json` und werden als Docker-Secret eingebunden.
- Die Texte liegen als gemountete HTML-Fragmente unter `config/legal/` und
  können ohne Rebuild und ohne Neustart geändert werden.
- Ohne gültige Konfiguration erscheinen keine Links; die Seiten liefern `404`.
- Die Rechtsseiten sind öffentlich erreichbar und werden nicht indexiert.

## Dateien

```text
config/
  impressum.json          # persönliche Daten, gitignored
  impressum.json.sample   # Vorlage
  legal/
    impressum.html        # gemounteter Text, gitignored
    impressum.html.sample # Vorlage
    datenschutz.html
    datenschutz.html.sample
```

## Konfiguration anlegen

```bash
cp config/impressum.json.sample config/impressum.json
cp config/legal/impressum.html.sample config/legal/impressum.html
cp config/legal/datenschutz.html.sample config/legal/datenschutz.html
```

`config/impressum.json` ausfüllen:

```json
{
  "name": "Max Mustermann",
  "street": "Musterstraße 1",
  "postal_code": "12345",
  "city": "Musterstadt",
  "country": "Deutschland",
  "email": "kontakt@example.org",
  "phone": "",
  "updated": "2026-11-08"
}
```

Pflichtfelder sind `name`, `street`, `postal_code`, `city`, `country`, `email`
und `updated`. `phone` ist optional. Die Platzhalter in den HTML-Dateien werden
beim Rendern automatisch HTML-escaped.

Rechte für den Auth-Container (UID/GID `10001`):

```bash
chown 10001:10001 config/impressum.json
chmod 600 config/impressum.json
chown -R 10001:10001 config/legal
chmod 600 config/legal/*.html
```

## Compose

Im `auth`-Service ergänzen:

```yaml
services:
  auth:
    environment:
      IMPRINT_FILE: /run/secrets/imprint
      LEGAL_DIR: /app/legal
    volumes:
      - ./config/legal:/app/legal:ro
    secrets:
      - imprint

secrets:
  imprint:
    file: ./config/impressum.json
```

`config/legal` ist kein Secret, sondern ein read-only Bind-Mount. Änderungen an
den Texten sind dadurch sofort aktiv, weil der Auth-Service die Dateien bei
jedem Aufruf neu liest.

## Server-Logs: 30 Tage

Die Datenschutzerklärung nennt 30 Tage für Server-Logs. Das muss auf dem Server
tatsächlich umgesetzt sein.

Docker-Logging in der Compose-Datei begrenzen:

```yaml
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
```

Zusätzlich hostseitig `logrotate` für die Docker-Logs konfigurieren, zum
Beispiel unter `/etc/logrotate.d/docker-containers`:

```text
/var/lib/docker/containers/*/*-json.log {
    daily
    rotate 30
    compress
    missingok
    copytruncate
    delaycompress
}
```

Die nginx-Logs von `web` werden seit dieser Änderung nach `stdout`/`stderr`
geschrieben und damit ebenfalls vom Docker-Logging erfasst. Traefik-Logs sind
separat zu konfigurieren; auch dort müssen 30 Tage gelten.

Falls der non-root nginx `/dev/stdout` bzw. `/dev/stderr` nicht öffnen kann,
die Logs wieder nach `/var/log/nginx/` schreiben, dieses Verzeichnis auf den
Host mounten und in die Logrotate-Konfiguration aufnehmen.

## Deployment

```bash
docker compose config
docker compose build auth web
docker compose up -d --force-recreate auth web
docker compose ps
docker compose logs --tail=100 auth web
```

## Verifikation

```bash
# Loginseite: Links nur bei Konfiguration
curl -sS https://karte.jfr-service.de/login | grep -E 'datenschutz|impressum'

# Rechtsseiten sind öffentlich
curl -sSI https://karte.jfr-service.de/impressum | \
  grep -iE 'HTTP/|content-type|cache-control|x-robots-tag'
curl -sS https://karte.jfr-service.de/impressum | grep -E 'Impressum|Nominatim'
curl -sS https://karte.jfr-service.de/datenschutz | grep -E 'Contabo|BayLDA|30 Tage'

# Status für den Karten-Footer
curl -sS https://karte.jfr-service.de/legal-status
# erwartet: {"imprint":true,"privacy":true}
```

Im Browser prüfen:

- Loginseite zeigt den kleinen Footer unten in der Karte.
- Karte zeigt „Datenschutz“ und „Impressum“ unten mittig.
- Auf schmalen Displays überdeckt der Footer nicht die Leaflet-Attribution.
- Ohne Konfiguration (z. B. `IMPRINT_FILE` entfernt) erscheinen keine Links und
  die Rechtsseiten liefern `404`.

## Offline-Verhalten

- Die Karte selbst bleibt über den Service Worker und IndexedDB offline nutzbar.
- Die Rechtslinks werden auf Karte und Offline-Seite nur angezeigt, wenn
  `/legal-status` erreichbar ist. Beim `offline`-Event werden sie sofort
  ausgeblendet, beim `online`-Event wieder geprüft.
- Die Rechtsseiten selbst werden nicht im Service-Worker-Cache gespeichert,
  damit keine veralteten Rechtstexte ausgeliefert werden.
- Wird offline eine Rechtsseite aufgerufen, liefert der Service Worker die
  gecachte `offline.html` aus, statt einen Browser-Fehlercode anzuzeigen.
- Eine bereits geöffnete Rechtsseite bleibt offline lesbar; nach einem Reload
  greift der Offline-Fallback.
- Der Zurück-Link der Rechtsseiten zeigt auf `/`. Online führt er je nach
  Sitzung zur Karte oder zur Anmeldung, offline auf die Offline-Seite.

## Textpflege ohne Rebuild

1. `config/legal/impressum.html` oder `config/legal/datenschutz.html` bearbeiten.
2. Seite neu laden.

Die Dateien werden bei jedem Aufruf gelesen. Ein Rebuild oder Neustart ist nicht
nötig. Änderungen an `config/impressum.json` (persönliche Daten) werden beim
Start geladen; dafür reicht:

```bash
docker compose restart auth
```

## Deaktivieren

- `IMPRINT_FILE` entfernen oder die Secret-Datei umbenennen: Beide Rechtsseiten
  werden deaktiviert, die Links verschwinden.
- Einzelne Seite deaktivieren: die entsprechende HTML-Datei aus
  `config/legal/` entfernen oder umbenennen. Der zugehörige Link wird
  ausgeblendet, die Seite liefert `404`.

## Datenschutzhinweis zu den Caches

Die ausgelieferte `vmforum_members.json` enthält keine Ortsangaben, sondern nur
Koordinaten. Auf dem Server werden die Rohdaten mit Ortsangabe für die
Geocodierung zwischengespeichert:

- Mitgliederdaten-Cache: 7 bis 14 Tage
- Nominatim-Cache: 180 bis 365 Tage, negative Treffer 30 Tage

Diese Speicherung ist in der Datenschutzerklärung benannt. Die Fehlermeldungen
des Grabbers geben die Ortsangabe seit dieser Änderung nicht mehr im Klartext
aus.

## Rollback

```bash
docker compose stop auth web
docker tag "${COMPOSE_PROJECT_NAME}_auth:latest" \
  "${COMPOSE_PROJECT_NAME}_auth:rollback-$(date -u +%Y%m%d%H%M%S)"
# vorherigen Stand auschecken und neu bauen
docker compose build auth web
docker compose up -d --force-recreate auth web
```

Der Service Worker erhöht `CACHE_NAME`; nach einem Rollback im Browser
`?dev=1` aufrufen oder die Website-Daten löschen.
