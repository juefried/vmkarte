# OAuth2-Teststand: Übergabe, Produktionsübernahme und Sync

**Stand:** 08.11.2026

**Test-Branch:** `release/oauth2-test`

**Produktions-Branch:** `release/3.0-pwa`

Dieses Dokument beschreibt, wie der OAuth2-Teststand später in die Produktion
übernommen wird und wie die Testinstallation mit Weiterentwicklungen aus dem
Release-Branch synchron gehalten wird.

## 1. Ausgangslage

Die Testinstanz läuft unter:

```text
https://karte-test.jfr-service.de
```

Sie nutzt:

- OAuth2-Authorization-Code-Flow über das Velomobilforum,
- Scope `user:read`,
- `/api/me/` zur Ermittlung von `user_id` und `username`,
- ein eigenes Docker-Compose-Projekt `vmkarte-oauth-test`,
- eigene Secrets unter `config/`,
- die produktiv erzeugten Kartendaten ausschließlich read-only.

Der Produktivbetrieb läuft unter `karte.jfr-service.de` und bleibt unberührt.

## 2. Branch-Modell

- `release/oauth2-test` ist ein temporärer Integrations- und Deployment-Branch.
- `release/3.0-pwa` ist der Produktions-Release-Branch.
- Der Test-Branch basiert auf dem Merge-Base-Commit `412f1da`.
- Der Release-Branch hat sich seitdem weiterentwickelt (u. a. Suchfunktionen,
  `search-filter.js`, `search-fit.js`, Service-Worker-Cache v17 sowie
  Data-Grabber-Änderungen).

### Test-Branch-Commits

| Commit | Inhalt |
|---|---|
| `0dca8b2` | Test-Compose, Test-Doku, Test-Konfiguration |
| `e0e5339` | OAuth2-Login im Auth-Service |
| `3f6a653` | nginx: Query-String bei Auth-Routen erhalten |
| `c1d3001` | OAuth-Token-Fehlerdetails loggen |
| `2e15deb` | Doku: Secret-Datei enthält nur den Wert |
| `b9827ef` | `OAUTH_AUTO_REDIRECT`, Loginseite als Default, Logout-Meldung |

## 3. Fachliche Änderungen vs. Test-Deployment

### In die Produktion übernehmen

| Datei | Änderung |
|---|---|
| `docker/auth/main.go` | OAuth2-Flow, State-Cookie, Token-Tausch, `/api/me/`, Logout-Meldung, `OAUTH_AUTO_REDIRECT` |
| `docker/auth/main_test.go` | Tests für den OAuth2-Flow |
| `docker/webserver/default.conf` | Routen `/auth/forum/login`, `/auth/forum/callback`; `$is_args$args` bei Auth-Routen |
| `docker/webserver/www_data/js/app.js` | Logout-Ziel `/login?local=1&loggedout=1` |
| `docker/webserver/Dockerfile` | optional: `APP_TITLE`, `APP_SHORT_NAME`, `SERVER_NAME` mit produktiven Defaults |
| `README.md` | optional: Verweis auf eine Produktions-OAuth-Doku |

Die Dockerfile-Erweiterung ist optional. Der OAuth2-Flow funktioniert auch ohne
sie. Sie ist nur nötig, wenn die Produktion denselben konfigurierbaren
Browser-/PWA-Titel und `server_name` verwenden soll.

### Nicht in die Produktion übernehmen

| Datei | Grund |
|---|---|
| `docker-compose.yml` | Testprojekt, Testdomain, Traefik-Host, Test-Volume |
| `.env.sample` | Testwerte und Testdomain |
| `config/oauth_client_secret.sample` | Test-Kontext |
| `config/session_signing_key.sample` | Test-Kontext |
| `docs/deploy-oauth-test.md` | Test-Deployment-Doku |
| `config/oauth_client_secret` | echtes Secret, nur auf dem Testserver |
| `config/.htpasswd`, `config/session_signing_key`, `.env` | Laufzeitdateien, nie committen |

Die produktive `docker-compose.yml` liegt auf dem Server und muss manuell um
OAuth-Variablen und das Secret ergänzt werden. Sie darf nicht durch die
Test-Compose-Datei ersetzt werden.

## 4. Produktionsübernahme

### 4.1 Produktions-Client anfordern

Bei Reinhard einen eigenen Produktions-Client anfordern:

```text
Redirect-URI: https://karte.jfr-service.de/auth/forum/callback
Scope:        user:read
Client-Typ:   vertrauliche Server-Webanwendung
```

Den Test-Client danach deaktivieren bzw. löschen lassen. Das Test-Secret wird
nicht wiederverwendet.

### 4.2 Arbeitsbranch und Merge

Keine direkten Commits auf `release/3.0-pwa`. Stattdessen:

```bash
git fetch origin
git switch -c feature/oauth2-production origin/release/3.0-pwa
```

Dann die fachlichen Änderungen aus `release/oauth2-test` übernehmen. Wegen der
Weiterentwicklungen im Release-Branch ist ein Cherry-Pick der fachlichen Commits
oder eine gezielte Dateiübernahme sicherer als ein pauschaler Merge.

Details stehen im Prompt:

```text
docs/prompts/merge-oauth2-into-release-3.0-pwa.md
```

### 4.3 Konflikte

Aktuell überlappen sich nur:

- `README.md`
- `docker/webserver/www_data/js/app.js`

Beim Merge gilt:

- Release-Änderungen an `app.js` (Suche, Autofit, Pin-Verhalten) vollständig
  behalten.
- Danach nur die Logout-Zeile auf `/login?local=1&loggedout=1` ändern.
- `README.md` aus dem Release übernehmen und nur den Produktions-OAuth-Link
  ergänzen.
- `docker/webserver/default.conf` um die OAuth-Routen und `$is_args$args`
  ergänzen; bestehende Release-Änderungen nicht überschreiben.
- `docker/webserver/Dockerfile` nur übernehmen, wenn der konfigurierbare Titel
  und `server_name` auch produktiv gewünscht sind.

### 4.4 Produktive Konfiguration

Auf dem Produktivserver in der dortigen `docker-compose.yml` ergänzen:

```yaml
environment:
  OAUTH_CLIENT_ID: <produktive-client-id>
  OAUTH_CLIENT_SECRET_FILE: /run/secrets/oauth_client_secret
  OAUTH_AUTHORIZE_URL: https://www.velomobilforum.de/forum/index.php?oauth2/authorize
  OAUTH_TOKEN_URL: https://www.velomobilforum.de/forum/index.php?api/oauth2/token
  OAUTH_USERINFO_URL: https://www.velomobilforum.de/forum/index.php?api/me/
  OAUTH_SCOPE: user:read
  OAUTH_REDIRECT_URI: https://karte.jfr-service.de/auth/forum/callback
  OAUTH_AUTO_REDIRECT: "false"
secrets:
  - oauth_client_secret
```

Secret:

```yaml
secrets:
  oauth_client_secret:
    file: ./config/oauth_client_secret
```

Das Secret gehört auf dem Server nach `config/oauth_client_secret`, mit
`chown 10001:10001` und `chmod 600`. Es darf nicht in Git und nicht in
`.env.sample` oder Doku stehen.

### 4.5 `OAUTH_AUTO_REDIRECT`

Empfehlung für den Produktiv-Rollout:

1. Start mit `OAUTH_AUTO_REDIRECT=false`.
   Die Loginseite mit OAuth-Button und lokalem Fallback erscheint.
2. OAuth für alle Nutzer beobachten.
3. Erst wenn OAuth stabil läuft, auf `true` wechseln.
4. Lokalen Formular-Fallback erst danach entfernen.

Ein vollständiges Forum-Logout beim Abmelden aus der Karte ist **nicht**
gewünscht. Der lokale Logout beendet nur die Kartensitzung.

### 4.6 Verifikation

```bash
docker compose config
docker compose build auth web
docker compose up -d
docker compose ps
docker compose logs --tail=100 auth web
```

Danach prüfen:

- `https://karte.jfr-service.de` zeigt bei `OAUTH_AUTO_REDIRECT=false` die
  Loginseite.
- OAuth-Login führt zurück zur Karte.
- Logout führt auf die Loginseite mit „Du wurdest abgemeldet.“.
- Lokaler Fallback funktioniert weiterhin.
- Geschützte Daten ohne Sitzung liefern `401`.
- Traefik-Router und TLS funktionieren.

## 5. Token-Widerruf beim Logout

Gewünscht ist:

- lokale Kartensitzung beenden,
- OAuth-Access-/Refresh-Token widerrufen,
- Forum-Sitzung **nicht** beenden.

Der Widerruf erfolgt über:

```text
POST https://www.velomobilforum.de/forum/index.php?api/oauth2/revoke
client_id=<id>
client_secret=<secret>
token=<access- oder refresh-token>
token_type_hint=access_token|refresh_token
```

Dafür müssen die Tokens serverseitig verfügbar sein. Der aktuelle
Session-Cookie ist stateless und enthält keine Tokens. Mögliche Umsetzungen:

- In-Memory-Store im Auth-Service, keyed by zufälliger Session-ID:
  einfach, aber bei Container-Neustart gehen die Tokens verloren.
- Persistenter Store (kleine Datei oder SQLite):
  widerstandsfähiger, aber zusätzlicher Zustand.
- Token im verschlüsselten Cookie:
  nicht empfohlen.

Der Widerruf sollte beim Logout best effort erfolgen: Fehler loggen, lokale
Sitzung trotzdem beenden. Ein Forum-Logout-Redirect ist nicht Teil des Ziels.

Dieser Punkt ist auf dem Test-Branch **nicht implementiert** und bleibt eine
Produktionsaufgabe.

## 6. Testinstallation mit dem Release synchron halten

Die Testinstallation soll vor allem Änderungen im Webmodul aus
`release/3.0-pwa` übernehmen, damit sie sich wie die Produktion verhält.

Zu synchronisieren:

- `docker/webserver/www_data/js/app.js`
- `docker/webserver/www_data/js/search-filter.js`
- `docker/webserver/www_data/js/search-fit.js`
- `docker/webserver/www_data/service-worker.js`
- `tests/frontend/search-filter.test.js`
- `tests/frontend/search-fit.test.js`
- optional: `README.md` und Data-Grabber-Änderungen

Dabei beibehalten:

- OAuth2-Code in `docker/auth/`
- OAuth-Routen und `$is_args$args` in `docker/webserver/default.conf`
- Test-Titel und `SERVER_NAME` in `docker/webserver/Dockerfile`
- `docker-compose.yml`, `.env.sample`, `config/*.sample`
- `docs/deploy-oauth-test.md`
- Logout-Ziel in `app.js`: `/login?local=1&loggedout=1`

Nach dem Sync:

```bash
docker compose build web
docker compose up -d web
docker compose exec web nginx -t
node --test tests/frontend/*.test.js
```

Danach Karte, Suche, OAuth-Login, Logout und Fallback testen.

Der passende Prompt steht unter:

```text
docs/prompts/sync-oauth2-test-with-release-3.0-pwa.md
```

## 7. Sicherheit und Aufräumen

- Das Test-Secret ist ausschließlich für die Testumgebung bestimmt.
- Beim Einstellen der Testumgebung:
  - `config/oauth_client_secret` löschen,
  - Test-Client bei Reinhard deaktivieren/löschen lassen,
  - Test-Container und Test-Volumes entfernen.
- Produktions-Client und Produktions-Secret getrennt halten.
- Secrets nie in Git, Docs oder Tickets ablegen.
- Das Produktions-Secret nur als Docker-Secret oder geschützte Laufzeitdatei
  bereitstellen.

## 8. Prompts

- Produktionsübernahme:
  `docs/prompts/merge-oauth2-into-release-3.0-pwa.md`
- Sync Test aus Release:
  `docs/prompts/sync-oauth2-test-with-release-3.0-pwa.md`
