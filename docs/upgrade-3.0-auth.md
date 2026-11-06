# Release 3.0 – Auth-Service und nginx-Schutz

**Stand:** 06.11.2026  
**Branch:** `release/3.0-pwa`

Diese Anleitung beschreibt das Deployment der ersten Ausbaustufe:

- Go-Auth-Service
- formularbasierte Anmeldung
- signiertes Session-Cookie
- nginx `auth_request`
- Schutz von Karte und Mitgliederdaten
- Entfernung von HTTP Basic Authentication

Enthalten seit Phase 5: Frontend-Datenloader mit IndexedDB, dauerhafte
Datenstatusanzeige, ETag-Abgleich und manueller Refresh.

Enthalten seit Phase 7: Service Worker, App-Shell-Cache, Offline-Reload und
kontrollierter Update-Hinweis.

Enthalten seit Phase 6: PWA-Manifest, Icons und Installierbarkeit.

Enthalten seit Phase 8: Standortanzeige nach Klick sowie lokale Speicherung und
Wiederherstellung von Kartenausschnitt, Zoom und Filtern.

Enthalten seit Phase 9: App-Version mit Build-Datum, Update-Erkennung,
Entwicklungsmodus mit Cache-Bypass sowie Deployment- und Rollback-Dokumentation.

Noch nicht enthalten: Domainumzug.

## Voraussetzungen

- Docker und Docker Compose
- Traefik mit Entrypoint `websecure` und Certresolver `leresolver`
- Traefik und `web` im externen Netz `traefik_proxy`
- `web` ist über `web:8080` erreichbar
- Zugriff auf `config/`

## Backup

```bash
cd /pfad/zu/vmkarte
cp docker-compose.yml docker-compose.yml.bak-phase3
cp -a docker/webserver/default.conf docker/webserver/default.conf.bak-phase3
cp -a docker/webserver/nginx.conf docker/webserver/nginx.conf.bak-phase3
cp -a config config.bak-phase3
```

## bcrypt-Passwortdatei

Die bisherige Datei enthält Apache MD5 (`$apr1$`). Der Auth-Service benötigt bcrypt.

```bash
docker run --rm -it httpd:2.4-alpine htpasswd -nB -C 12 BENUTZER
```

`BENUTZER` durch den bisherigen gemeinsamen Benutzernamen ersetzen (oder einen
neuen festlegen und im Forum kommunizieren). `-nB` zeigt den Hash an und fragt
interaktiv nach dem Passwort. Kein `-b` verwenden: Das würde die Passwortabfrage
unterdrücken und eine Passwortangabe auf der Kommandozeile erwarten.

Die Ausgabe in `config/.htpasswd` eintragen:

```text
BENUTZER:$2y$12$...
```

Der Hash enthält `$`-Zeichen. Am besten einen Editor verwenden und keine
Shell-Expansion auslösen.

Prüfen:

```bash
grep -c ':\$2[aby]\$' config/.htpasswd
# erwartet: 1
```

Falls für denselben Benutzer noch eine alte `$apr1$`-Zeile vorhanden ist:
Der Auth-Service bevorzugt die letzte bcrypt-Zeile. Besser ist trotzdem, die
alte Zeile zu entfernen und nur eine bcrypt-Zeile pro Benutzer zu behalten.

## Passwort wird nicht akzeptiert

Zuerst die Datei im Container prüfen (zeigt nur Zeilennummer, Benutzername,
Hash-Präfix und Länge, nicht den Hash):

```bash
docker compose exec auth \
  awk -F: '{print NR, $1, substr($2,1,4), length($2)}' \
  /run/secrets/htpasswd
```

Erwartet: genau eine passende Zeile mit Präfix `$2y$` oder `$2b$` und einer
Länge von etwa 60 Zeichen. Ein Eintrag mit Präfix `$apr` und Länge 37 ist
Apache MD5 und wird vom Auth-Service nicht akzeptiert.

Hash und Passwort unabhängig mit Apache prüfen:

```bash
docker run --rm -it \
  -v "$PWD/config/.htpasswd:/tmp/.htpasswd:ro" \
  httpd:2.4-alpine htpasswd -v /tmp/.htpasswd BENUTZER
```

Falls das fehlschlägt, die Zeile direkt in der Datei aktualisieren:

```bash
docker run --rm -it \
  -v "$PWD/config:/config" \
  httpd:2.4-alpine htpasswd -B -C 12 /config/.htpasswd BENUTZER

sudo chown 10001:10001 config/.htpasswd
sudo chmod 600 config/.htpasswd

docker compose up -d --force-recreate auth
```

Der Login-Benutzername muss exakt dem Benutzernamen in der Datei entsprechen
(Groß-/Kleinschreibung beachten).

## Signaturschlüssel

```bash
openssl rand -base64 48 > config/session_signing_key
sudo chown 10001:10001 config/.htpasswd config/session_signing_key
sudo chmod 600 config/.htpasswd config/session_signing_key
```

Der Auth-Container läuft als UID/GID `10001`. Da Compose-Secrets als
Bind-Mounts umgesetzt werden, müssen die Dateien für diese UID lesbar sein.
`chown 10001:10001` plus `chmod 600` ist restriktiver als `chmod 644`.

Der Schlüssel bleibt außerhalb von Git. Rotation macht alle Sitzungen ungültig.

## Compose

Die bestehende serverseitige `docker-compose.yml` anpassen:

- `auth`-Service ergänzen
- `auth` ohne veröffentlichten Port und ohne Traefik-Labels
- `web` veröffentlicht keinen Host-Port mehr; Traefik erreicht es über `web:8080`
- `.htpasswd`-Mount aus `web` entfernen
- Compose-Secrets für `.htpasswd` und `session_signing_key`
- Traefik-Service-Port von `80` auf `8080` ändern

Wesentliche Ausschnitte:

```yaml
services:
  web:
    build:
      context: docker/webserver
    image: localhost/${COMPOSE_PROJECT_NAME}_web:latest

    # Kein ports:-Eintrag. Traefik erreicht den Container über traefik_proxy.
    expose:
      - "8080"

    volumes:
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
      - ./docker/webserver/www_data/shared:/www_data/shared:ro

    depends_on:
      auth:
        condition: service_healthy

    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.${COMPOSE_PROJECT_NAME}-secure.entrypoints=websecure"
      - "traefik.http.routers.${COMPOSE_PROJECT_NAME}-secure.rule=Host(`karte.jfr-service.de`)"
      - "traefik.http.routers.${COMPOSE_PROJECT_NAME}-secure.tls=true"
      - "traefik.http.routers.${COMPOSE_PROJECT_NAME}-secure.tls.certresolver=leresolver"
      - "traefik.http.routers.${COMPOSE_PROJECT_NAME}-secure.service=${COMPOSE_PROJECT_NAME}"
      - "traefik.http.services.${COMPOSE_PROJECT_NAME}.loadbalancer.server.port=8080"
      - "traefik.http.services.${COMPOSE_PROJECT_NAME}.loadbalancer.server.scheme=http"
      - "traefik.http.routers.${COMPOSE_PROJECT_NAME}-secure.middlewares=${COMPOSE_PROJECT_NAME}"
      - "traefik.http.middlewares.${COMPOSE_PROJECT_NAME}.headers.STSPreload=true"
      - "traefik.http.middlewares.${COMPOSE_PROJECT_NAME}.headers.STSSeconds=31536000"
      - "traefik.docker.network=traefik_proxy"

    networks:
      - traefik_proxy
      - default

  auth:
    build:
      context: docker/auth
    image: localhost/${COMPOSE_PROJECT_NAME}_auth:latest
    expose:
      - "8080"
    environment:
      PASSWORD_FILE: /run/secrets/htpasswd
      SESSION_KEY_FILE: /run/secrets/session_signing_key
    secrets:
      - htpasswd
      - session_signing_key
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8080/health"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 5s
    restart: unless-stopped

secrets:
  htpasswd:
    file: ./config/.htpasswd
  session_signing_key:
    file: ./config/session_signing_key
```

`auth` bleibt ausschließlich im `default`-Netz. `web` ist in `default` und
`traefik_proxy`; daher funktioniert `proxy_pass http://auth:8080`.

`auth` wird wie `web` über `build.context` und einen lokalen Image-Namen gebaut.
`docker compose build` baut beide Images; `docker compose build web auth`
baut gezielt nur diese beiden.

## Traefik

Traefik terminiert TLS und setzt `X-Forwarded-For`, `X-Forwarded-Host` und
`X-Forwarded-Proto`. Der Karten-nginx vertraut dem Traefik-Netz
`172.16.0.0/12`; das Traefik-Netz `traefik_proxy` liegt in diesem Bereich.

Wichtig:

- `traefik.http.services.${COMPOSE_PROJECT_NAME}.loadbalancer.server.port=8080`
- `web` nicht mehr über einen Host-Port veröffentlichen
- `traefik.docker.network=traefik_proxy` beibehalten
- keine Basic-Auth-Middleware auf dem Karten-Router

HSTS wird von Traefik gesetzt. In `docker/webserver/security-headers.conf` ist
die HSTS-Zeile deshalb auskommentiert.

Traefik erlaubt in dieser Installation `allowEncodedSlash` und
`allowEncodedQuestionMark` global. Der Karten-nginx lehnt kodierte Pfadtrenner
im Pfad zusätzlich mit `400` ab; Query-Parameter bleiben davon unberührt.

HTTPS muss an Traefik terminiert werden. Das Session-Cookie ist im
Produktivbetrieb `Secure`.

nginx löst `auth:8080` über den Docker-DNS-Server `127.0.0.11` mit
`valid=10s` dynamisch auf. Dadurch führt ein Neu-Erstellen des
`auth`-Containers nicht mehr zu einer veralteten Upstream-IP. Ein
`web`-Restart nach einem Auth-Restart ist dann nicht mehr nötig.

`absolute_redirect off;` hält nginx-Weiterleitungen relativ. Ohne diese Option
würde nginx die interne Portnummer `8080` in `Location`-Header schreiben und
der Browser würde auf `https://karte.jfr-service.de:8080/...` umgeleitet.

## Start

```bash
docker compose build web auth cron
docker compose up -d
docker compose ps
docker compose logs --tail=100 auth web
```

## Frontend-Dateien (Phase 5)

Die Karte lädt zusätzlich:

- `/js/app.js`, `/js/data.js`, `/js/storage.js`, `/js/status-ui.js`,
  `/js/map-state.js`, `/js/location.js`, `/js/geo-handler.js`
- `/css/app.css`
- `/geo-handler.html` bzw. `/geo-handler` für `geo:`-Links
- weiterhin `/leaflet/` und `/markercluster/`

Diese statischen Dateien sind öffentlich erreichbar. Geschützt bleiben `/`,
`/karte.html` und `/shared/`. Der Datenstand wird aus
`/shared/data-status.json` gelesen, die Mitgliederdaten aus
`/shared/vmforum_members.json`; beide Routen laufen über `auth_request`.

`/js/` und `/css/` liefern `Cache-Control: no-cache`. Dadurch werden Updates
sofort revalidiert (ETag/`304`), statt bis zu einer Stunde aus dem
Browser-Cache zu kommen.

`data-status.json` enthält:

```json
{
  "runStartedAt": "2026-11-06T03:33:00+01:00",
  "generatedAt": "2026-11-06T03:41:12+01:00",
  "memberCount": 3275
}
```

Das Frontend nutzt `generatedAt` für die Anzeige und die 48-h-Warnung,
`runStartedAt` nur als Zusatzinformation im Tooltip. Der zuletzt geladene Stand
wird in IndexedDB gespeichert und bei Logout und `401` gelöscht. Die
Statusanzeige blendet nach einigen Sekunden aus und erscheint bei Änderungen
erneut; bei fehlender Verbindung bleibt ein Offline-Badge sichtbar.

Die CSP enthält für Skripte nur noch `script-src 'self'`. `style-src` behält
`'unsafe-inline'`, weil Leaflet Inline-Stile setzt.

`data-status.json` muss für den nginx-User lesbar sein. Der Grabber schreibt die
Datei mit `0644`. Bei bestehenden Installationen prüfen:

```bash
ls -l docker/webserver/www_data/shared/data-status.json
# erwartet: -rw-r--r-- (0644)
chmod 644 docker/webserver/www_data/shared/data-status.json
```

Der `geo:`-Protokollhandler zeigt auf `/geo-handler?l=%s` (same-origin).
`geo-handler.html` und `js/geo-handler.js` leiten gültige Koordinaten zu
BRouter weiter. `geo-handler.php` ist nur noch eine Legacy-Datei.

## Service Worker und Offline (Phase 7)

- `/service-worker.js` wird beim Laden der Karte registriert (Scope `/`).
- Der Service-Worker-Cache (aktuell `vmkarte-shell-v7`) enthält App-Shell
  (`/`, `/karte.html`), CSS/JS, Leaflet, MarkerCluster, `geo-handler.html` und
  `offline.html`. Seit Phase 8 sind auch `js/map-state.js` und `js/location.js`
  enthalten; seit Phase 9 zusätzlich `js/version.js` und
  `js/version-check.js`.
- Navigationen laufen network-first mit Cache-/`offline.html`-Fallback.
- Statische Assets laufen stale-while-revalidate.
- `/shared/`, `/login`, `/logout` und `/_internal/session-check` bleiben
  network-only. `data-status.json` wird dadurch nie gecacht.
- Login-Weiterleitungen werden nicht als App-Shell gecacht
  (`response.redirected`).
- Logout und `401` löschen IndexedDB und alle Cache-Storage-Einträge mit
  Präfix `vmkarte-`.
- Ein Update wird erst nach Klick auf „Neu laden“ aktiv (`SKIP_WAITING`).
- Bei Änderungen an App-Dateien `CACHE_NAME` in `service-worker.js` erhöhen,
  damit Clients den neuen Worker installieren.
- Phase 6 (Manifest und Icons) ist umgesetzt; die Karte ist als PWA
  installierbar.

Prüfen:

```bash
curl -sSI https://karte.jfr-service.de/service-worker.js | \
  grep -iE 'service-worker-allowed|cache-control|content-type'
# erwartet: Service-Worker-Allowed: /, Cache-Control: no-cache
```

## PWA-Manifest und Icons (Phase 6)

- `/manifest.webmanifest` ist öffentlich und wird als
  `application/manifest+json` mit `Cache-Control: no-cache` ausgeliefert.
- Manifest:
  - `name: Velomobil-Forum Karte`, `short_name: VMKarte`
  - `start_url: /karte.html`, `scope: /`, `display: standalone`
  - `theme_color: #1565c0`, `background_color: #ffffff`
- Icons:
  - `/icons/icon-192.png` (192×192, any)
  - `/icons/icon-512.png` (512×512, any)
  - `/icons/icon-maskable-512.png` (512×512, maskable)
  - `/icons/apple-touch-icon.png` (180×180)
- `karte.html` bindet Manifest, Theme-Farbe, Favicon und Apple-Touch-Icon ein.
- `/icons/` und `/screenshots/` sind öffentlich mit `expires 7d`;
  `/favicon.ico` zeigt auf `/icons/icon-192.png`.
- Screenshots für die reichere Install-UI:
  - `/screenshots/screenshot-wide.png` (1280×720, `form_factor: wide`)
  - `/screenshots/screenshot-narrow.png` (390×844, `form_factor: narrow`)
  - Die Screenshots enthalten nur fiktive Testmarker.
- Der Service-Worker-Cache (aktuell `vmkarte-shell-v7`) enthält Manifest, Icons
  und Screenshots.
- Bei künftigen App-Änderungen `CACHE_NAME` in `service-worker.js` erhöhen.
- Quellen der Icons: `icons/icon-any.svg` und `icons/icon-maskable.svg`.

Prüfen:

```bash
curl -sSI https://karte.jfr-service.de/manifest.webmanifest | \
  grep -iE 'HTTP/|content-type|cache-control'
# erwartet: 200, application/manifest+json, Cache-Control: no-cache

curl -sSI https://karte.jfr-service.de/icons/icon-192.png | \
  grep -iE 'HTTP/|content-type'
# erwartet: 200, image/png

curl -sSI https://karte.jfr-service.de/screenshots/screenshot-wide.png | \
  grep -iE 'HTTP/|content-type'
# erwartet: 200, image/png
```

Danach im Browser (Chrome/Edge) die Installationsaufforderung prüfen; auf
Android/iPhone „Zum Home-Bildschirm“ verwenden.

## Standort und Kartenstatus (Phase 8)

- Der Standortbutton steht in der Aktionsleiste der Suche, als vorletzter
  Button direkt vor „Abmelden“.
- `navigator.geolocation.getCurrentPosition()` wird ausschließlich im
  Click-Handler aufgerufen; es gibt kein `watchPosition` und keine dauerhafte
  Verfolgung.
- Marker und Genauigkeitskreis erscheinen nur nach erfolgreicher Abfrage. Die
  Karte wird einmalig auf die Position zentriert.
- Berechtigung verweigert, nicht verfügbar und Timeout werden als
  verständliche deutsche Meldungen angezeigt.
- Standortdaten werden nicht an den App-Server übertragen, nicht in
  IndexedDB/`localStorage` gespeichert und nicht in die URL geschrieben.
  Solange der Kartenmittelpunkt der zuletzt ermittelten Position entspricht,
  wird er nicht als `mapState.center` gespeichert; das gilt auch nach Zoom,
  Resize und für verspätete Save-Timer.
- Kartenmitte, Zoom und der aktuelle URL-Filterstand werden unter dem
  IndexedDB-Schlüssel `mapState` im Store `kv` gespeichert.
- Beim Start werden Karte und Zoom wiederhergestellt. URL-Filter haben Vorrang;
  ohne URL-Filter wird der gespeicherte Filterstand per URL angewendet.
- Dropdown und Suchfeld starten immer im Default-Zustand; der Freitext wird
  nicht gespeichert.
- Logout und `401` leeren IndexedDB, melden den Service Worker ab und löschen
  die `vmkarte-`-Caches. Der Service Worker registriert sich beim nächsten
  Kartenaufruf neu.
- `CACHE_NAME` ist `vmkarte-shell-v7`.

## Version und Update (Phase 9)

Die App-Version wird beim Docker-Build erzeugt. Quelle ist die gepflegte Datei
`docker/webserver/www_data/VERSION`; sie enthält genau eine Zeile, zum Beispiel
`3.0.1`. Das Dockerfile schreibt daraus:

- `/app-version.json` für die Laufzeitprüfung:

  ```json
  {"version":"3.0.1","buildDate":"2026-11-06T10:15:00Z"}
  ```

- `/js/version.js` als importierbares Modul mit `APP_VERSION` und
  `BUILD_DATE`.

Ein normaler Build übernimmt die Version aus `VERSION` und erzeugt das
Build-Datum automatisch:

```bash
docker compose build web
```

Optional lassen sich beide Werte überschreiben:

```bash
APP_VERSION=$(git describe --tags --always --dirty) \
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
docker compose build web
```

Ohne Docker bleiben die eingecheckten Dev-Fallbacks (`dev`, kein Build-Datum)
aktiv. Sie dienen nur lokalen Tests und werden im Image überschrieben.

Beim Start lädt `js/app.js` `/app-version.json` mit `cache: 'no-store'`. Die
laufende Version stammt aus `js/version.js`. Der Vergleich ist eine exakte
String-Ungleichheit; es findet kein SemVer-Parsing statt. Nur bei
unterschiedlicher Version erscheint der Hinweis „Eine neue Version ist
verfügbar.“ mit der Aktion „Neu laden“. Es gibt keinen automatischen Reload.

Der bestehende Service-Worker-Hinweis und der App-Version-Hinweis sind
zusammengeführt:

- Existiert ein wartender Service Worker, wird nach Bestätigung
  `SKIP_WAITING` gesendet und nach `controllerchange` neu geladen.
- Andernfalls wird `registration.update()` angestoßen und bis zu 3 Sekunden auf
  einen wartenden Worker gewartet. Gibt es danach keinen wartenden Worker,
  werden vor dem Neuladen die `vmkarte-`-Caches gelöscht und der Service Worker
  abgemeldet, damit der Reload garantiert frische Dateien lädt.
- Schlägt der Abruf von `/app-version.json` fehl (offline oder HTTP-Fehler),
  bleibt die Karte ohne Meldung nutzbar.

`/app-version.json` ist im Service Worker network-only und wird nicht gecacht.
Der nginx-Block liefert bereits `application/json` und
`Cache-Control: no-store`.

`VERSION` und `CACHE_NAME` müssen bei einer Release-Änderung gemeinsam erhöht
werden. `VERSION` steuert den Update-Hinweis; `CACHE_NAME` sorgt dafür, dass der
Service Worker die geänderten App-Dateien neu lädt.

## Entwicklungsmodus und Cache-Löschung

### Entwicklungsmodus

`?dev=1` aktiviert den Entwicklungsmodus für die aktuelle Tab-Session
(`sessionStorage`), `?dev=0` deaktiviert ihn wieder. Ohne Parameter bleibt der
zuletzt gesetzte Zustand dieser Tab-Session erhalten.

Im Entwicklungsmodus:

- werden vorhandene Service-Worker-Registrierungen abgemeldet,
- werden alle Cache-Storage-Einträge mit Präfix `vmkarte-` gelöscht,
- wird kein neuer Service Worker registriert,
- wird die App-Version nicht geprüft,
- erscheint die Meldung „Entwicklungsmodus aktiv: Service Worker und
  App-Caches sind deaktiviert.“

Der Modus betrifft nur App-Caches. IndexedDB mit den zuletzt geladenen
Kartendaten bleibt erhalten und wird weiterhin bei Logout und `401` gelöscht.
`/js/` und `/css/` liefern `Cache-Control: no-cache`; Navigationen laufen
network-first. Ein normaler Reload im Entwicklungsmodus lädt daher frische
Dateien.

Die vollständige Wirkung tritt nach dem nächsten Reload ein: `unregister()`
beendet einen bereits aktiven Controller nicht sofort. Bis zum Reload kann die
aktuelle Seite noch vom bisherigen Service Worker bedient werden. Die
App-Caches werden bei jedem Aufruf mit `?dev=1` erneut gelöscht.

Logout und `401` ändern den Entwicklungsmodus nicht. Wer nach dem Abmelden
wieder im normalen Modus arbeiten möchte, ruft `?dev=0` auf.

### Cache-Löschung für Nutzer

- Bei einem Update-Hinweis „Neu laden“ bestätigen. Erst danach wird die neue
  Version aktiv.
- Wenn die App trotzdem veraltet wirkt: im Browser die Website-Daten für
  `karte.jfr-service.de` löschen (Chrome/Edge: Einstellungen → Datenschutz →
  Website-Daten; Safari: Website-Daten verwalten) und die Seite neu öffnen.
- Auf installierten PWAs hilft zusätzlich, die App zu schließen und neu zu
  starten, damit der neue Service Worker übernimmt.

### Cache-Löschung für Entwickler

`?dev=1` ist der einfachste Weg. Alternativ in den DevTools:

1. Application → Service Workers: bestehende Worker abmelden.
2. Application → Storage → Clear site data.
3. Oder in der Konsole:

```js
Promise.all(
  (await caches.keys())
    .filter(key => key.startsWith('vmkarte-'))
    .map(key => caches.delete(key))
);
navigator.serviceWorker.getRegistrations()
  .then(registrations => registrations.forEach(registration => registration.unregister()));
```

Nach einem Wechsel von `CACHE_NAME` installiert der neue Worker den Cache beim
nächsten Kartenaufruf neu.

## Deployment und Rollback (Release 3.0)

### Deployment

Nur das `web`-Image ändern; `auth` und `cron` bleiben unberührt.

```bash
docker compose build web
docker compose up -d --force-recreate web
docker compose ps
```

Prüfen:

```bash
curl -sS https://karte.jfr-service.de/app-version.json
curl -sSI https://karte.jfr-service.de/app-version.json | \
  grep -iE 'HTTP/|content-type|cache-control'
```

Erwartet: `{"version":"3.0.1","buildDate":"…"}`, `application/json` und
`Cache-Control: no-store`.

Nach dem Deployment im Browser prüfen:

- Die Karte lädt normal.
- `?dev=1` zeigt die Dev-Meldung und meldet den Service Worker ab.
- Eine Testversion mit erhöhter Version zeigt nach dem Deployment den
  Update-Hinweis; neu geladen wird erst nach Klick.

### Rollback

Vor einem Deployment das bisherige Image sichern:

```bash
docker tag "${COMPOSE_PROJECT_NAME}_web:latest" \
  "${COMPOSE_PROJECT_NAME}_web:rollback-$(date -u +%Y%m%d%H%M%S)"
```

Rollback auf das gesicherte Image:

```bash
docker compose stop web
docker tag "${COMPOSE_PROJECT_NAME}_web:rollback-<zeitstempel>" \
  "${COMPOSE_PROJECT_NAME}_web:latest"
docker compose up -d --force-recreate web
docker compose ps
```

Alternativ den vorherigen Release-Commit auschecken und neu bauen:

```bash
git switch --detach <vorheriger-release-commit>
docker compose build web
docker compose up -d --force-recreate web
```

Nach dem Rollback im Browser `?dev=1` aufrufen, um alte Caches zu entfernen,
oder die Website-Daten löschen. Der Service Worker erhöht `CACHE_NAME` nicht
rückwärts; deshalb ist die zusätzliche Cache-Löschung beim Rollback wichtig.

## Tests

```bash
# Auth darf nicht veröffentlicht sein
docker compose port auth 8080

# Ohne Sitzung
curl -i https://karte.jfr-service.de/
# 302 /login?next=/

curl -i https://karte.jfr-service.de/shared/vmforum_members.json
# 401 {"error":"unauthorized"}

# Login
read -r VMKARTE_USER
read -s VMKARTE_PASSWORD
curl -i -c cookies.txt -b cookies.txt \
  -X POST https://karte.jfr-service.de/login \
  --data-urlencode "username=$VMKARTE_USER" \
  --data-urlencode "password=$VMKARTE_PASSWORD" \
  --data-urlencode 'next=/'
unset VMKARTE_USER VMKARTE_PASSWORD

# -c cookies.txt legt die Cookie-Datei an; -b liest sie.
# Die Datei liegt im aktuellen Arbeitsverzeichnis.
# Nach den Tests: rm -f cookies.txt

# Mit Sitzung
curl -i -b cookies.txt https://karte.jfr-service.de/shared/vmforum_members.json
# 200

# Interner Pfad
curl -i https://karte.jfr-service.de/_internal/session-check
# 404

# Kodierter Pfadtrenner wird für die Karte abgelehnt
curl -i 'https://karte.jfr-service.de/shared%2Fvmforum_members.json'
# 400

# Logout
curl -i -b cookies.txt -c cookies.txt -X POST https://karte.jfr-service.de/logout
curl -i -b cookies.txt https://karte.jfr-service.de/shared/vmforum_members.json
# 401
```

Rate Limit prüfen:

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://karte.jfr-service.de/login \
    --data-urlencode 'username=BENUTZER' \
    --data-urlencode 'password=falsch'
done
# nach einigen Versuchen: 429
```

Im nginx-Access-Log muss `$remote_addr` die echte Client-IP sein, nicht
`172.18.x.x`. Andernfalls greift das Rate Limit für alle Nutzer gemeinsam.

Danach im Browser `https://karte.jfr-service.de` öffnen und anmelden.

## Logout

Die Karte hat im Suchfeld-Panel einen Button **Abmelden**. Er sendet
`POST /logout`, löscht das Session-Cookie und leitet auf `/login` weiter.

Ein direkter Aufruf von `GET /logout` im Browser löscht das Cookie ebenfalls
und leitet auf `/login` weiter. Für die Oberfläche bleibt `POST /logout` der
bevorzugte Weg; `GET /logout` ist nur eine Komfortfunktion für direkte
URL-Aufrufe.

## Troubleshooting: HTTP 500 nach Auth-Neustart

Im nginx-Log steht:

```text
connect() failed (111: Connection refused) ... upstream: "http://172.x.x.x:8080/session-check"
```

Dann hält eine ältere `web`-Version noch die alte Auth-IP. Einmalig:

```bash
docker compose up -d --force-recreate web
```

Mit der aktuellen nginx-Konfiguration löst `resolver 127.0.0.11 valid=10s`
den Namen `auth` dynamisch auf; dieser Web-Restart ist dann nicht mehr nötig.

## Troubleshooting: `auth` startet mit `permission denied`

Im Log steht beispielsweise:

```text
ERROR cannot load session signing key error="open /run/secrets/session_signing_key: permission denied"
```

Dann kann der Container-Benutzer `10001` die Secret-Datei nicht lesen.
Compose-Secrets werden als Bind-Mounts umgesetzt und behalten die
Dateirechte des Hosts.

```bash
sudo chown 10001:10001 config/.htpasswd config/session_signing_key
sudo chmod 600 config/.htpasswd config/session_signing_key
docker compose up -d --force-recreate auth
docker compose logs --tail=20 auth
```

## Rollback der Auth-Umstellung (Phase 3)

Der Release-weite Rollback für Version 3.0 steht im Abschnitt „Deployment und
Rollback (Release 3.0)“. Die folgenden Schritte stellen nur die
Auth-/nginx-Umstellung aus Phase 3 zurück.

```bash
docker compose down
cp docker-compose.yml.bak-phase3 docker-compose.yml
cp docker/webserver/default.conf.bak-phase3 docker/webserver/default.conf
cp docker/webserver/nginx.conf.bak-phase3 docker/webserver/nginx.conf
docker compose build web
docker compose up -d
```

Falls Basic Auth wieder aktiviert werden soll, den `.htpasswd`-Mount im
`web`-Service und die `auth_basic`-Direktiven aus dem Backup wiederherstellen.

## Hinweise

- `COOKIE_SECURE` ist standardmäßig `true`. Für lokale HTTP-Tests muss
  `COOKIE_SECURE=false` gesetzt oder HTTPS verwendet werden.
- Die CSP enthält vorübergehend `script-src 'unsafe-inline'`, weil das
  bestehende `karte.html` noch Inline-JavaScript verwendet. Das wird in der
  Frontend-Phase entfernt.
- HSTS wird ausschließlich von Traefik gesetzt.
- Kodierte Pfadtrenner (`%2F`, `%3F`) werden für die Karte mit `400` abgelehnt.
- Die alte Domain wird in dieser Ausbaustufe noch nicht weitergeleitet.
