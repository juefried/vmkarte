# Prompt: Testinstallation mit `release/3.0-pwa` synchronisieren

Du arbeitest im Repository `vmkarte`. Aktualisiere die Testinstallation auf
Basis von `release/oauth2-test` mit den Weiterentwicklungen aus
`release/3.0-pwa`, insbesondere im Webmodul. Die OAuth2-Funktionen und die
Test-Deployment-Konfiguration müssen unverändert erhalten bleiben.

## Kontext

- Test-Branch: `release/oauth2-test`
- Produktions-Branch: `release/3.0-pwa`
- Gemeinsamer Merge-Base: `412f1da`
- Der Release-Branch hat seitdem u. a. folgende Web-Änderungen:
  - `docker/webserver/www_data/js/app.js` (Suche, Autofit, Pin-Verhalten)
  - `docker/webserver/www_data/js/search-filter.js` (neu)
  - `docker/webserver/www_data/js/search-fit.js` (neu)
  - `docker/webserver/www_data/service-worker.js` (Cache v17)
  - `tests/frontend/search-filter.test.js` (neu)
  - `tests/frontend/search-fit.test.js` (neu)
- Der Test-Branch enthält zusätzlich:
  - OAuth2-Code in `docker/auth/`
  - OAuth-Routen in `docker/webserver/default.conf`
  - `$is_args$args` für Auth-Routen
  - Test-Titel und `SERVER_NAME` in `docker/webserver/Dockerfile`
  - Logout-Ziel `/login?local=1&loggedout=1` in `app.js`
  - Test-Compose, Test-`.env`, Test-Secrets, Test-Doku

## Ziel

- Webmodul der Testinstallation auf den Release-Stand bringen.
- OAuth2-Login, Logout, Fallback und Test-Deployment nicht beschädigen.
- Keine Test-Konfiguration durch Release-Dateien überschreiben.
- Keine Produktionsdateien ändern.

## Arbeitsbranch

Keine direkten Commits auf `release/3.0-pwa`.

```bash
git status
git fetch origin
git switch -c chore/sync-oauth2-test-from-release release/oauth2-test
```

## Ausgangsstand prüfen

```bash
git log --oneline --decorate --max-count=10
git merge-base HEAD origin/release/3.0-pwa
git diff --stat 412f1da..origin/release/3.0-pwa
git diff --stat 412f1da..release/oauth2-test
```

## Webmodul gezielt übernehmen

Empfohlen ist die gezielte Dateiübernahme, nicht ein pauschaler Merge.

```bash
git checkout origin/release/3.0-pwa -- \
  docker/webserver/www_data/js/app.js \
  docker/webserver/www_data/js/search-filter.js \
  docker/webserver/www_data/js/search-fit.js \
  docker/webserver/www_data/service-worker.js \
  tests/frontend/search-filter.test.js \
  tests/frontend/search-fit.test.js
```

Danach in `docker/webserver/www_data/js/app.js` die Logout-Zeile wieder
anwenden:

- Release-Version: `window.location.assign('/login');`
- Test-Version: `window.location.assign('/login?local=1&loggedout=1');`

Prüfen:

```bash
grep -nE 'search-filter|search-fit' docker/webserver/www_data/js/app.js
grep -nE "window.location.assign\('/login" docker/webserver/www_data/js/app.js
grep -nE 'CACHE_NAME' docker/webserver/www_data/service-worker.js
```

Erwartet:

- Suchmodule werden verwendet.
- Logout zeigt auf `/login?local=1&loggedout=1`.
- `CACHE_NAME` ist der Release-Stand (aktuell `vmkarte-shell-v17`).

## Test-spezifische Dateien nicht überschreiben

Nicht aus dem Release übernehmen bzw. danach unverändert lassen:

- `docker/auth/main.go`
- `docker/auth/main_test.go`
- `docker/webserver/default.conf`
- `docker/webserver/Dockerfile`
- `docker-compose.yml`
- `.env.sample`
- `config/oauth_client_secret.sample`
- `config/session_signing_key.sample`
- `docs/deploy-oauth-test.md`
- `docs/oauth2-test-handover.md`
- `docs/prompts/*`

Prüfen:

```bash
grep -nE 'auth/forum/login|auth/forum/callback|is_args' \
  docker/webserver/default.conf
grep -nE 'OAUTH_|vmkarte-oauth-test' docker-compose.yml .env.sample
grep -nE 'APP_TITLE|APP_SHORT_NAME|SERVER_NAME' \
  docker/webserver/Dockerfile
```

## Optionale Übernahmen

- `README.md`: Nur übernehmen, wenn die Release-Doku-Änderungen gewünscht sind.
  Den Test-Link auf `docs/deploy-oauth-test.md` erhalten.
- `src/data_grabber/*`: Für den Testbetrieb nicht nötig, weil dort kein Cron
  läuft. Nur übernehmen, wenn der Test-Checkout auch für Grabber-Tests genutzt
  wird.
- `tests/browser/*.mjs`: Optional für Browser-Tests.

## Tests

```bash
node --test tests/frontend/*.test.js

cd docker/auth
go test ./...
cd ../..
```

Falls lokal kein Go installiert ist:

```bash
docker run --rm -v "$PWD/docker/auth:/src" -w /src \
  golang:1.23-alpine go test ./...
```

## Deployment auf der Testinstanz

```bash
cd /home/docker.run/velomobilforum-karte-oauth-test
git pull
docker compose build web
docker compose up -d web
docker compose ps
docker compose exec web nginx -t
```

## Manuelle Prüfung

1. Karte und Suche funktionieren wie in der Produktion.
2. OAuth-Login funktioniert weiterhin.
3. Logout führt auf `/login?local=1&loggedout=1` mit „Du wurdest abgemeldet.“.
4. Lokaler Fallback `/login?local=1` funktioniert.
5. Keine Testdomain, kein Test-Secret und keine Test-Compose wurde beschädigt.
6. Service Worker lädt die neue Version; ggf. im Browser `?dev=1` zum
   Cache-Leeren verwenden.

## Commit und Pull Request

```bash
git status
git diff --check
git add docker/webserver/www_data/js/app.js \
  docker/webserver/www_data/js/search-filter.js \
  docker/webserver/www_data/js/search-fit.js \
  docker/webserver/www_data/service-worker.js \
  tests/frontend/search-filter.test.js \
  tests/frontend/search-fit.test.js
# optional: README.md, tests/browser/*.mjs, src/data_grabber/*
git commit -m "chore(test): sync web module from release/3.0-pwa"
git push -u origin chore/sync-oauth2-test-from-release
```

Pull Request gegen `release/oauth2-test` öffnen. Erst nach Prüfung mergen.

## Abschlussbericht

Berichte:

- übernommene Web-Dateien,
- Bestätigung, dass OAuth- und Test-Deployment-Dateien unverändert sind,
- Testergebnisse,
- Service-Worker-Version,
- durchgeführte manuelle Prüfungen,
- offene Punkte.
