# Release 3.0 – OAuth2-Anmeldung über das Velomobil-Forum

**Stand:** 08.11.2026
**Branch:** `release/3.0-pwa`

Diese Anleitung beschreibt die produktive OAuth2-Anmeldung im Auth-Service.

- OAuth2-Authorization-Code-Flow über das Velomobil-Forum
- Scope `user:read`
- Benutzerermittlung über `/api/me/`
- Login-Seite mit OAuth-Button und lokalem Formular-Fallback
- nginx-Routen für `/auth/forum/login` und `/auth/forum/callback`
- Logout leitet auf `/login?local=1&loggedout=1`

Der bisherige Formular-Login bleibt als lokaler Fallback erhalten.

## Produktions-Client

Beim Betreiber des Velomobil-Forums einen eigenen Produktions-Client anfordern:

```text
Redirect-URI: https://karte.jfr-service.de/auth/forum/callback
Scope:        user:read
Client-Typ:   vertrauliche Server-Webanwendung
```

Der Test-Client der Testumgebung wird nicht wiederverwendet. Nach der
Umstellung den Test-Client deaktivieren bzw. löschen lassen.

## Secret bereitstellen

Das Client-Secret gehört ausschließlich auf den Produktionsserver. Es wird
nicht in Git, nicht in `.env` und nicht in der Doku abgelegt.

```bash
nano config/oauth_client_secret
```

In dieser Datei steht nur der Wert, nicht `OAUTH_CLIENT_SECRET=...`.

Rechte für den Auth-Container (UID/GID `10001`) setzen:

```bash
chown 10001:10001 config/oauth_client_secret
chmod 600 config/oauth_client_secret
```

Das Secret wird als Docker-Secret `oauth_client_secret` eingebunden und vom
Auth-Service über `OAUTH_CLIENT_SECRET_FILE=/run/secrets/oauth_client_secret`
gelesen.

## Compose konfigurieren

Die serverseitige `docker-compose.yml` liegt nicht im Repository und darf nicht
durch eine Test-Compose-Datei ersetzt werden. Im `auth`-Service ergänzen:

```yaml
services:
  auth:
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

secrets:
  oauth_client_secret:
    file: ./config/oauth_client_secret
```

| Variable | Bedeutung |
|---|---|
| `OAUTH_CLIENT_ID` | Client-ID der XenForo-OAuth2-App |
| `OAUTH_CLIENT_SECRET_FILE` | Pfad zur Secret-Datei im Container |
| `OAUTH_AUTHORIZE_URL` | XenForo-Authorization-Endpunkt |
| `OAUTH_TOKEN_URL` | XenForo-Token-Endpunkt |
| `OAUTH_USERINFO_URL` | XenForo-API-Endpunkt für den angemeldeten Benutzer |
| `OAUTH_SCOPE` | Benötigter Scope, aktuell `user:read` |
| `OAUTH_REDIRECT_URI` | Exakt beim Client registrierte Callback-URL |
| `OAUTH_AUTO_REDIRECT` | `false`: Login-Seite anzeigen; `true`: direkt zum Forum weiterleiten |

`OAUTH_AUTO_REDIRECT` hat den Default `false`. Die Login-Seite erscheint dann
mit OAuth-Button und lokalem Fallback.

## nginx-Routen

`docker/webserver/default.conf` enthält die öffentlichen Routen:

- `/login`
- `/auth/forum/login`
- `/auth/forum/callback`

Bei allen Auth-Routen wird der Query-String mit `$is_args$args` erhalten. Der
OAuth-Callback mit `code` und `state` funktioniert nur mit dieser Ergänzung.

## Login-Seite

Die Login-Seite zeigt:

- „Karte Velomobil-Forum“
- „Anmeldung über Velomobil-Forum“
- „Alternativ als Fallback über die bisherigen Zugangsdaten:“

Der lokale Formular-Fallback bleibt zunächst erhalten und ist direkt unter
`/login?local=1` erreichbar.

## Logout

Der Logout-Button beendet nur die Kartensitzung und leitet auf
`/login?local=1&loggedout=1` weiter. Die Seite zeigt dann „Du wurdest
abgemeldet.“.

Ein vollständiges Logout aus dem Velomobil-Forum ist nicht gewünscht.

Ein Token-Widerruf beim Logout ist derzeit nicht implementiert. Der
Session-Cookie ist stateless und enthält keine OAuth-Tokens. Ein späterer
Widerruf müsste serverseitig Tokens vorhalten und `POST
https://www.velomobilforum.de/forum/index.php?api/oauth2/revoke` best effort
aufrufen.

## Rollout

Empfohlene Reihenfolge:

1. Mit `OAUTH_AUTO_REDIRECT=false` starten und die Login-Seite anzeigen.
2. OAuth-Anmeldung und lokalen Fallback beobachten.
3. Erst wenn OAuth stabil läuft, auf `OAUTH_AUTO_REDIRECT=true` wechseln.
4. Den lokalen Formular-Fallback erst danach entfernen.

## Deployment

```bash
docker compose config
docker compose build auth web
docker compose up -d
docker compose ps
docker compose logs --tail=100 auth web
```

## Verifikation

```bash
# Login-Seite (ohne Sitzung)
curl -sS https://karte.jfr-service.de/login | grep -E \
  'Karte Velomobil-Forum|Anmeldung über Velomobil-Forum|bisherigen Zugangsdaten'

# OAuth-Start leitet zum Forum
curl -sSI https://karte.jfr-service.de/auth/forum/login | \
  grep -iE 'HTTP/|location'

# Callback ohne Code wird abgelehnt bzw. auf den Fallback geleitet
curl -sSI https://karte.jfr-service.de/auth/forum/callback | \
  grep -iE 'HTTP/|location'

# Geschützte Daten ohne Sitzung
curl -sSI https://karte.jfr-service.de/shared/vmforum_members.json | \
  grep -iE 'HTTP/'
# erwartet: 401
```

Danach im Browser prüfen:

- Login-Seite zeigt die drei Texte.
- OAuth-Login führt zurück zur Karte.
- Lokaler Fallback funktioniert weiterhin.
- Logout führt auf die Login-Seite mit „Du wurdest abgemeldet.“.
- Suche, Autofit, Service Worker und Datenstatus funktionieren unverändert.

## Sicherheit

- Secret nur auf dem Server, nie in Git.
- Keine Testdomain und keine Test-Secrets in Produktionskonfiguration oder Doku.
- `config/oauth_client_secret` bleibt gitignoriert.
