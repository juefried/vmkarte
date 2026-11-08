# Prompt: OAuth2-Teststand nach `release/3.0-pwa` übernehmen

Du arbeitest im Repository `vmkarte`. Übernimm die fachlichen OAuth2-Änderungen
aus dem Branch `release/oauth2-test` in den Produktions-Release-Branch
`release/3.0-pwa`, ohne die Test-Deployment-Dateien zu übernehmen und ohne die
Weiterentwicklungen im Release-Branch zu verlieren.

## Kontext

- Test-Branch: `release/oauth2-test`
- Produktions-Branch: `release/3.0-pwa`
- Gemeinsamer Merge-Base: `412f1da`
- Der Release-Branch hat sich seit dem Merge-Base weiterentwickelt. Prüfe den
  aktuellen Stand mit `git fetch origin` und `git log`.
- Der Test-Branch enthält sowohl fachliche OAuth2-Änderungen als auch
  test-spezifische Deployment-Dateien.

## Ziel

- OAuth2-Login im Auth-Service.
- nginx-Routen für `/auth/forum/login` und `/auth/forum/callback`.
- Query-String-Erhalt bei Auth-Routen (`$is_args$args`).
- Logout-Ziel `/login?local=1&loggedout=1` in `app.js`.
- `OAUTH_AUTO_REDIRECT` mit Default `false`.
- Keine Test-Compose, keine Testdomain, keine Test-Secrets im Release-Branch.
- Bestehende Release-Funktionen (Suche, Autofit, Service Worker, Data Grabber)
  bleiben unverändert.

## Arbeitsbranch

Keine direkten Commits auf `release/3.0-pwa`.

```bash
git status
git fetch origin
git switch -c feature/oauth2-production origin/release/3.0-pwa
```

## Ausgangsstand prüfen

```bash
git log --oneline --decorate --max-count=20
git merge-base HEAD release/oauth2-test
git diff --stat 412f1da..release/oauth2-test
git diff --stat 412f1da..origin/release/3.0-pwa
```

Erwartete fachliche Test-Commits:

```text
e0e5339 feat(auth): add XenForo OAuth2 login
3f6a653 fix(web): preserve auth query strings in nginx proxy
c1d3001 fix(auth): include OAuth token endpoint error details
b9827ef feat(auth): make OAuth redirect configurable and improve logout
```

Nicht übernehmen:

```text
0dca8b2 chore(deploy): add OAuth2 test compose environment
2e15deb docs: clarify OAuth client secret file format
```

`2e15deb` betrifft nur die Test-Doku. Die Erkenntnis (Secret-Datei enthält nur
den Wert) gehört in die Produktions-Doku, nicht als Test-Doku in den Release.

## Dateien übernehmen

Empfohlener Weg: gezielte Dateiübernahme statt pauschalem Cherry-Pick, weil der
Test-Branch deployment-spezifische Dateien enthält.

Vorher prüfen, ob der Release-Branch dieselben Dateien seit dem Merge-Base
verändert hat:

```bash
git diff 412f1da..origin/release/3.0-pwa -- \
  docker/auth/main.go \
  docker/auth/main_test.go \
  docker/webserver/default.conf \
  docker/webserver/Dockerfile
```

Wenn diese Ausgabe leer ist, können die Testdateien gezielt übernommen werden.
Wenn nicht, die Release-Änderungen nicht überschreiben, sondern die
OAuth-Änderungen manuell in die Release-Version einarbeiten.

```bash
# Fachliche Auth- und nginx-Änderungen
git checkout release/oauth2-test -- \
  docker/auth/main.go \
  docker/auth/main_test.go \
  docker/webserver/default.conf
```

Optional, nur wenn der konfigurierbare Browser-/PWA-Titel und `server_name`
auch produktiv gewünscht sind:

```bash
git checkout release/oauth2-test -- docker/webserver/Dockerfile
```

Wenn die Dockerfile-Änderung übernommen wird, prüfen:

- `ARG APP_TITLE=Velomobil-Forum Karte`
- `ARG APP_SHORT_NAME=VMKarte`
- `ENV SERVER_NAME=_`
- Produktive Defaults bleiben unverändert.

Nicht übernehmen:

- `docker-compose.yml`
- `.env.sample`
- `config/oauth_client_secret.sample`
- `config/session_signing_key.sample`
- `docs/deploy-oauth-test.md`
- den Test-Link in `README.md`

## `app.js` gezielt anpassen

`app.js` im Release-Branch enthält neue Suchfunktionen. Nicht die Testversion
übernehmen. Nur die Logout-Zeile ändern:

- vorher: `window.location.assign('/login');`
- nachher: `window.location.assign('/login?local=1&loggedout=1');`

Danach prüfen, dass die Release-Suchfunktionen erhalten sind:

```bash
git diff -- docker/webserver/www_data/js/app.js
grep -nE 'search-filter|search-fit|/login\?local=1&loggedout=1' \
  docker/webserver/www_data/js/app.js
```

## Produktive Konfiguration dokumentieren

Die produktive `docker-compose.yml` liegt auf dem Server und ist nicht Teil
dieses Merges. Dokumentiere in einer neuen Produktions-Doku (z. B.
`docs/upgrade-3.0-oauth.md`):

- Produktions-Client mit Redirect-URI
  `https://karte.jfr-service.de/auth/forum/callback`
- OAuth-Variablen:
  - `OAUTH_CLIENT_ID`
  - `OAUTH_CLIENT_SECRET_FILE`
  - `OAUTH_AUTHORIZE_URL`
  - `OAUTH_TOKEN_URL`
  - `OAUTH_USERINFO_URL`
  - `OAUTH_SCOPE=user:read`
  - `OAUTH_REDIRECT_URI`
  - `OAUTH_AUTO_REDIRECT=false`
- Docker-Secret `oauth_client_secret`
- Secret nur auf dem Server, nie in Git
- lokaler Formular-Fallback bleibt zunächst erhalten
- Token-Widerruf beim Logout ist noch nicht implementiert
- vollständiges Forum-Logout ist nicht gewünscht

Verlinke in `README.md` nur diese Produktions-Doku, nicht
`docs/deploy-oauth-test.md`.

## Tests

```bash
# Go-Auth-Tests
cd docker/auth
go test ./...
cd ../..

# Frontend-Tests
node --test tests/frontend/*.test.js
```

Falls lokal kein Go installiert ist, die Tests in einem Go-Container ausführen:

```bash
docker run --rm -v "$PWD/docker/auth:/src" -w /src \
  golang:1.23-alpine go test ./...
```

Zusätzlich prüfen:

- `docker/webserver/default.conf` enthält die OAuth-Routen und
  `$is_args$args`.
- `docker/auth/main.go` enthält keine Testdomain und keine Test-Secrets.
- `app.js` enthält weiterhin die Release-Suchfunktionen.
- Keine Secrets oder Test-`.env`-Werte wurden übernommen.

## Commit und Pull Request

```bash
git status
git diff --check
git add docker/auth/main.go docker/auth/main_test.go \
  docker/webserver/default.conf docker/webserver/www_data/js/app.js
# optional: docker/webserver/Dockerfile
git commit -m "feat(auth): add OAuth2 login for production"
git push -u origin feature/oauth2-production
```

Öffne einen Pull Request gegen `release/3.0-pwa`. Den PR nicht mergen.

## Abschlussbericht

Berichte:

- übernommene Dateien,
- nicht übernommene Test-Dateien,
- Konflikte und deren Auflösung,
- Testergebnisse,
- offene Produktionsschritte (Client, Secret, Compose, Deployment),
- Bestätigung, dass keine Secrets im Diff sind.
