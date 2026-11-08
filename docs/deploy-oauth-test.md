# OAuth2-Testumgebung auf `karte-test.jfr-service.de`

**Branch:** `release/oauth2-test`

**Zweck:** Eigenständige Testinstanz zur Vorbereitung der späteren OAuth2-Anmeldung.

## 1. Zweck

Diese Instanz läuft parallel zum Produktivbetrieb und dient ausschließlich dem
Testen von Änderungen an Karte, Auth-Service und später OAuth2. Sie nutzt
dieselben erzeugten Kartendaten wie die Produktion, erzeugt aber keine eigenen.

Die OAuth2-Anmeldung über das Velomobilforum ist auf diesem Branch implementiert.
Der bisherige Formular-Login bleibt als lokaler Fallback erhalten und ist nur
noch unter `/login?local=1` direkt erreichbar.

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
config/oauth_client_secret
```

Sie sind gitignoriert und dürfen nicht eingecheckt werden.

Die eingecheckten Vorlagen sind:

```text
.env.sample
config/.htpasswd.sample
config/session_signing_key.sample
config/oauth_client_secret.sample
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
OAUTH_AUTHORIZE_URL=https://www.velomobilforum.de/forum/index.php?oauth2/authorize
OAUTH_TOKEN_URL=https://www.velomobilforum.de/forum/index.php?api/oauth2/token
OAUTH_USERINFO_URL=https://www.velomobilforum.de/forum/index.php?api/me/
OAUTH_SCOPE=user:read
OAUTH_REDIRECT_URI=https://karte-test.jfr-service.de/auth/forum/callback
```

Das Client-Secret steht nicht in `.env`, sondern in `config/oauth_client_secret`.
Es wird als Docker-Secret eingebunden und vom Auth-Service über
`OAUTH_CLIENT_SECRET_FILE=/run/secrets/oauth_client_secret` gelesen.

| Variable | Bedeutung |
|---|---|
| `COMPOSE_PROJECT_NAME` | Trennt Container, Netzwerke und Traefik-Namen vom Produktivprojekt |
| `VMKARTE_SHARED_DATA_DIR` | Host-Pfad der produktiven Kartendaten, read-only eingebunden |
| `TEST_APP_TITLE` | Browser-/App-Titel der Testinstanz |
| `TEST_APP_SHORT_NAME` | Kurzname im PWA-Manifest |
| `COOKIE_SECURE` | Muss bei HTTPS über Traefik `true` sein |
| `OAUTH_CLIENT_ID` | Client-ID aus der XenForo-OAuth2-App |
| `OAUTH_AUTHORIZE_URL` | XenForo-Authorization-Endpunkt |
| `OAUTH_TOKEN_URL` | XenForo-Token-Endpunkt |
| `OAUTH_USERINFO_URL` | XenForo-API-Endpunkt für den angemeldeten Benutzer |
| `OAUTH_SCOPE` | Benötigter Scope, aktuell `user:read` |
| `OAUTH_REDIRECT_URI` | Exakt registrierte Callback-URL |

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

Diese URL ist im OAuth2-Client bei Reinhard registriert und wird von nginx
öffentlich an den Auth-Service weitergeleitet.

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

# Client-ID in .env eintragen und OAuth-Endpunkte prüfen.
# Client-Secret separat ablegen (nano oder vi):
nano config/oauth_client_secret

# Passwort-Hash für velonaut interaktiv erzeugen
docker run --rm -it httpd:2.4-alpine htpasswd -nB -C 12 velonaut
# Ausgabe in config/.htpasswd eintragen

# Rechte für den Auth-Container (UID/GID 10001) setzen
chown 10001:10001 config/.htpasswd config/session_signing_key config/oauth_client_secret
chmod 600 .env config/.htpasswd config/session_signing_key config/oauth_client_secret
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
# erwartet: 302 auf /login?next=/

curl -I https://karte-test.jfr-service.de/login?next=/
# erwartet: 302 auf /auth/forum/login?next=%2F

curl -I "https://karte-test.jfr-service.de/login?local=1&next=/"
# erwartet: 200, Loginseite mit OAuth-Button und lokalem Fallback

curl -I https://karte-test.jfr-service.de/shared/vmforum_members.json
# erwartet: 401

curl -s https://karte-test.jfr-service.de/manifest.webmanifest | grep name
# erwartet: "Velomobilkarte Test"
```

Danach im Browser:

1. `https://karte-test.jfr-service.de` öffnen.
2. Der Browser landet beim Velomobilforum.
3. Dort mit einem normalen Forumskonto anmelden und die Freigabe erteilen.
4. Zurück auf der Karte prüfen, dass Karte und Datenstand laden.
5. `https://karte-test.jfr-service.de/login?local=1` prüfen: Der lokale
   Formular-Login mit `velonaut` muss weiterhin funktionieren.
6. Abmelden testen.

## 11. OAuth2-Ablauf

Implementiert sind:

- Authorization-Code-Flow über das Velomobilforum,
- Start unter `/auth/forum/login`,
- Callback unter `/auth/forum/callback`,
- `state`-Cookie mit Signatur und 10 Minuten Laufzeit,
- Token-Austausch über `?api/oauth2/token`,
- Benutzerabruf über `?api/me/` mit `Authorization: Bearer`,
- Validierung von `user_id` und `username`,
- Setzen des bestehenden signierten Session-Cookies,
- OAuth-Button auf der Loginseite,
- lokaler Formular-Fallback unter `/login?local=1`.

Nicht verwendet werden:

- OpenID Connect und ID-Token,
- PKCE (für diesen vertraulichen Client nicht erforderlich),
- serverseitige Speicherung von Access-/Refresh-Token.

Offener Punkt: Beim Logout wird derzeit nur das lokale Session-Cookie gelöscht.
Der Token-Widerruf über `?api/oauth2/revoke` muss nachgerüstet werden, sobald
Access-/Refresh-Token serverseitig gespeichert werden.

## 12. Merge-Regel

Der Branch `release/oauth2-test` enthält deployment-spezifische Dateien:

- `docker-compose.yml`
- `.env.sample`
- `config/session_signing_key.sample`
- `config/oauth_client_secret.sample`
- `docs/deploy-oauth-test.md`

Diese Dateien dürfen nicht per Merge nach `release/3.0-pwa` übernommen werden.
Später nur die fachlichen OAuth-Änderungen gezielt cherry-picken.

Die fachlichen Änderungen liegen in:

- `docker/auth/main.go`
- `docker/auth/main_test.go`
- `docker/webserver/default.conf`

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

### OAuth-Login landet auf `/login?local=1&error=oauth`

- `docker compose logs --tail=100 auth` prüfen.
- Prüfen, ob `OAUTH_CLIENT_ID` in `.env` gesetzt ist.
- Prüfen, ob `config/oauth_client_secret` existiert, `10001:10001` gehört und
  `0600` hat.
- Prüfen, ob die Redirect-URI exakt
  `https://karte-test.jfr-service.de/auth/forum/callback` lautet.
- Prüfen, ob der Scope `user:read` freigegeben ist.
- Prüfen, ob der Server den Token-Endpunkt erreichen kann.

### OAuth-Login läuft in einer Schleife

Symptom:

```text
/auth/forum/callback?code=...&state=... -> 303
/login?local=1&error=oauth&next=%2F    -> 303
/auth/forum/login?next=%2F              -> 303
```

Dann fehlen im Auth-Service die Query-Parameter. Ursache ist `proxy_pass` mit
einer Variable: nginx hängt den ursprünglichen Query-String nicht automatisch an.

Prüfen:

```bash
docker compose exec web wget -S -O - \
  'http://auth:8080/login?local=1&error=oauth&next=%2F' 2>&1 | head -n 10
# erwartet: HTTP/1.1 200 OK

curl -sS -D - -o /dev/null \
  'https://karte-test.jfr-service.de/login?local=1&error=oauth&next=%2F'
# erwartet nach dem Fix: HTTP/2 200, vorher 303
```

Die Auth-Routen in `docker/webserver/default.conf` müssen deshalb so aussehen:

```nginx
proxy_pass http://$auth_backend/login$is_args$args;
proxy_pass http://$auth_backend/auth/forum/login$is_args$args;
proxy_pass http://$auth_backend/auth/forum/callback$is_args$args;
```

Danach `docker compose build web` und `docker compose up -d web`.

### `permission denied` beim OAuth-Client-Secret

```bash
chown 10001:10001 config/oauth_client_secret
chmod 600 config/oauth_client_secret
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
