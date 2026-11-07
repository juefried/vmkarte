# OAuth2-Testumgebung auf `karte-test.jfr-service.de`

**Branch:** `release/oauth2-test`

**Zweck:** Eigenständige Testinstanz zur Vorbereitung der späteren OAuth2-Anmeldung.

## 1. Zweck

Diese Instanz läuft parallel zum Produktivbetrieb und dient ausschließlich dem
Testen von Änderungen an Karte, Auth-Service und später OAuth2. Sie nutzt
dieselben erzeugten Kartendaten wie die Produktion, erzeugt aber keine eigenen.

Die OAuth2-Anmeldung ist in diesem Stand **noch nicht implementiert**. Die
Variablen `OAUTH_*` sind nur vorbereitete Laufzeitplatzhalter. Der Login erfolgt
weiterhin über das Formular mit der eigenen `.htpasswd` der Testinstanz.

## 2. Abgrenzung zur Produktion

| Thema | Produktion | Testinstanz |
|---|---|---|
| Checkout | `/home/docker.run/velomobilforum-karte` | `/home/docker.run/velomobilforum-karte-oauth-test` |
| Branch | `release/3.0-pwa` | `release/oauth2-test` |
| Compose-Projekt | produktives Projekt | `vmkarte-oauth-test` |
| Domain | `karte.jfr-service.de` | `karte-test.jfr-service.de` |
| Datengrabber | vorhanden | **nicht vorhanden** |
| Nominatim | über Cron | **kein Zugriff** |
| XenForo-API | über Cron | **kein Zugriff** |
| Kartendaten | werden erzeugt | nur lesend eingebunden |
| Secrets | `config/` der Produktion | `config/` der Testinstanz |

Die Trennung erfolgt über Branch, separates Checkout, eigenes Compose-Projekt,
eigene Images, eigene Secrets und eigene Kartendaten-Einbindung.

## 3. Kein Datengrabber in der Testinstanz

Die Test-Compose-Datei enthält nur:

- `web`
- `auth`

Nicht enthalten sind `cron`, `data_grabber`, Nominatim oder eine Datenbank.
Dadurch benötigt die Testinstanz weder einen XenForo-API-Key noch einen
eigenen Nominatim-Zugang.

## 4. Gemeinsame Kartendaten

Die Testinstanz bindet den produktiv erzeugten Shared-Data-Ordner ausschließlich
read-only ein:

```text
/home/docker.run/velomobilforum-karte/docker/webserver/www_data/shared
        -> /www_data/shared:ro
```

Der Auth-Service erhält keinen Zugriff auf diesen Pfad. Der Test-Stack darf den
gemeinsamen Datenbestand nicht schreiben, löschen oder verändern.

Der Pfad wird über `VMKARTE_SHARED_DATA_DIR` in `.env` gesetzt und ist nicht in
der Compose-Datei fest verdrahtet.

Wichtig: Nicht den Shared-Data-Ordner des Test-Checkouts verwenden. Dieser ist
leer und wird vom Test-Stack nicht befüllt.

Die Dateien müssen für den nginx-User der Testinstanz lesbar sein. Üblich sind
`0644` für Dateien und `0755` für Verzeichnisse. Der Test-Stack ändert daran
nichts.

## 5. Benötigte lokale Dateien

Im Test-Checkout müssen folgende Dateien existieren:

```text
.env
config/.htpasswd
config/session_signing_key
```

Sie sind gitignoriert und dürfen nicht eingecheckt werden.

Die eingecheckten Vorlagen sind:

```text
.env.sample
config/.htpasswd.sample
config/session_signing_key.sample
```

## 6. Umgebungsvariablen

`.env` wird von Docker Compose automatisch geladen.

```dotenv
COMPOSE_PROJECT_NAME=vmkarte-oauth-test
VMKARTE_SHARED_DATA_DIR=/home/docker.run/velomobilforum-karte/docker/webserver/www_data/shared
TEST_APP_TITLE=Velomobilkarte Test
TEST_APP_SHORT_NAME=VMKarte Test
COOKIE_SECURE=true

OAUTH_CLIENT_ID=
OAUTH_CLIENT_SECRET=
OAUTH_AUTHORIZE_URL=
OAUTH_TOKEN_URL=
OAUTH_REDIRECT_URI=https://karte-test.jfr-service.de/auth/forum/callback
```

| Variable | Bedeutung |
|---|---|
| `COMPOSE_PROJECT_NAME` | Trennt Container, Netzwerke und Traefik-Namen vom Produktivprojekt |
| `VMKARTE_SHARED_DATA_DIR` | Host-Pfad der produktiven Kartendaten, read-only eingebunden |
| `TEST_APP_TITLE` | Browser-/App-Titel der Testinstanz |
| `TEST_APP_SHORT_NAME` | Kurzname im PWA-Manifest |
| `COOKIE_SECURE` | Muss bei HTTPS über Traefik `true` sein |
| `OAUTH_CLIENT_ID` | Platzhalter für die spätere OAuth2-Client-ID |
| `OAUTH_CLIENT_SECRET` | Platzhalter für das spätere OAuth2-Client-Secret |
| `OAUTH_AUTHORIZE_URL` | Platzhalter für den späteren Authorization-Endpunkt |
| `OAUTH_TOKEN_URL` | Platzhalter für den späteren Token-Endpunkt |
| `OAUTH_REDIRECT_URI` | Spätere Callback-URL |

Die `OAUTH_*`-Variablen werden vom Auth-Service derzeit nicht gelesen.

## 7. Domain, DNS und Traefik

Die Testinstanz erwartet:

```text
karte-test.jfr-service.de
```

Erforderlich:

- DNS-Eintrag `karte-test.jfr-service.de` auf denselben Server,
- Traefik mit Entrypoint `websecure` und Certresolver `leresolver`,
- externes Docker-Netz `traefik_proxy`.

Traefik erreicht den Webserver über `web:8080`. Es wird **kein** Host-Port
veröffentlicht. Der Auth-Service ist ausschließlich im projektinternen
`default`-Netz und wird von Traefik nicht gesehen.

Die spätere OAuth2-Callback-URL lautet:

```text
https://karte-test.jfr-service.de/auth/forum/callback
```

Sie ist derzeit noch nicht implementiert. Der Catch-all in nginx liefert für
diesen Pfad noch `404`.

Der Hostname ist bewusst fest eingetragen, analog zum Produktivprojekt. Bei
einer Änderung müssen diese Stellen angepasst werden:

- Traefik-Regel in `docker-compose.yml`
- `SERVER_NAME` beim `web`-Service in `docker-compose.yml`
- `OAUTH_REDIRECT_URI` in `.env`

## 8. Erstinbetriebnahme

```bash
cd /home/docker.run/velomobilforum-karte-oauth-test

# Repo in das leere Verzeichnis klonen
git clone git@github.com:juefried/vmkarte.git .
git switch release/oauth2-test

# Lokale Konfiguration anlegen
cp .env.sample .env
cp config/.htpasswd.sample config/.htpasswd
openssl rand -base64 48 > config/session_signing_key

# Passwort-Hash für velonaut interaktiv erzeugen
docker run --rm -it httpd:2.4-alpine htpasswd -nB -C 12 velonaut
# Ausgabe in config/.htpasswd eintragen

# Rechte für den Auth-Container (UID/GID 10001) setzen
chown 10001:10001 config/.htpasswd config/session_signing_key
chmod 600 .env config/.htpasswd config/session_signing_key
```

Den produktiven Shared-Data-Pfad bei Bedarf verifizieren:

```bash
cd /home/docker.run/velomobilforum-karte
docker inspect "$(docker compose ps -q web)" \
  --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

Der Wert für `/www_data/shared` muss dem `VMKARTE_SHARED_DATA_DIR` in der
Test-`.env` entsprechen.

## 9. Start, Logs und Stoppen

```bash
cd /home/docker.run/velomobilforum-karte-oauth-test

# Konfiguration prüfen
docker compose config

# Bauen und starten
docker compose up -d --build

# Status
docker compose ps

# Logs
docker compose logs -f

# Stoppen
docker compose down
```

`COMPOSE_PROJECT_NAME` kommt aus `.env`; es sind kein `-p`, `-f` oder
`--env-file` nötig, solange die Befehle im Test-Checkout ausgeführt werden.

## 10. Prüfschritte nach dem Start

```bash
# Nur web und auth
docker compose config --services

# Keine veröffentlichten Host-Ports
docker compose port web 8080
docker compose port auth 8080

# Shared-Data ist im Container lesbar
docker compose exec web ls -l /www_data/shared/vmforum_members.json

# Web intern erreichbar
docker compose exec web wget -qO- http://127.0.0.1:8080/manifest.webmanifest

# Über Traefik
curl -I https://karte-test.jfr-service.de/
# erwartet: 302 auf /login

curl -I https://karte-test.jfr-service.de/shared/vmforum_members.json
# erwartet: 401

curl -s https://karte-test.jfr-service.de/manifest.webmanifest | grep name
# erwartet: "Velomobilkarte Test"
```

Danach im Browser `https://karte-test.jfr-service.de` öffnen und mit `velonaut`
und dem gesetzten Passwort anmelden.

## 11. OAuth2-Status

Nicht implementiert sind weiterhin:

- Authorization-Code-Flow,
- Callback-Route,
- PKCE,
- `state`-Validierung,
- Token-Austausch,
- Forum-Menüpunkt,
- Änderungen am XenForo-Forum.

Der Formular-Login bleibt in dieser Ausbaustufe der aktive Anmeldemechanismus.

## 12. Merge-Regel

Der Branch `release/oauth2-test` enthält deployment-spezifische Dateien:

- `docker-compose.yml`
- `.env.sample`
- `config/session_signing_key.sample`
- `docs/deploy-oauth-test.md`

Diese Dateien dürfen nicht per Merge nach `release/3.0-pwa` übernommen werden.
Später nur die fachlichen OAuth-Änderungen gezielt cherry-picken.

Die Erweiterung in `docker/webserver/Dockerfile` ist so gebaut, dass die
produktiven Defaults unverändert bleiben (`Velomobil-Forum Karte`, `_` als
`server_name`). Sie kann bei Bedarf separat übernommen werden.

Der Produktiv-Checkout darf nicht auf `release/oauth2-test` umgestellt werden.

## 13. Troubleshooting

### `auth` startet mit `permission denied`

```bash
chown 10001:10001 config/.htpasswd config/session_signing_key
chmod 600 config/.htpasswd config/session_signing_key
docker compose up -d --force-recreate auth
docker compose logs --tail=20 auth
```

### Traefik liefert 404 oder 502

- Prüfen, ob `karte-test.jfr-service.de` auf den Server zeigt.
- Prüfen, ob das externe Netz `traefik_proxy` existiert.
- Prüfen, ob der Container im Netz `traefik_proxy` hängt.
- Traefik-Logs und Router-Konfiguration prüfen.

### Karte meldet fehlende Daten

- Prüfen, ob `VMKARTE_SHARED_DATA_DIR` auf den produktiven Shared-Ordner zeigt.
- Prüfen, ob `vmforum_members.json` und `data-status.json` dort lesbar sind.
- Der Test-Stack erzeugt diese Dateien nicht selbst.
