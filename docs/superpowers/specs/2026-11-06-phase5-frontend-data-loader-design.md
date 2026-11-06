# Phase 5 – Frontend-Datenloader (Design)

**Datum:** 2026-11-06  
**Branch:** `release/3.0-pwa`  
**Bezug:** `local/ai/requirements.md`, `local/ai/phases.md`

## Absicht

Die Karte soll nach dem Umbau sofort benutzbar sein: zuerst der lokal gespeicherte
Datenstand, parallel ein Abgleich mit dem Server. Der Datenstand ist dauerhaft,
aber dezent sichtbar und eindeutig als **Server** oder **lokal** gekennzeichnet.
Ein manueller Refresh lädt die aktuelle Serverdatei ohne HTTP-Cache.

## Ziele

- `karte.html` wird App-Shell; CSS und JavaScript werden ausgelagert.
- Inline-JavaScript, Inline-CSS und `onLoad`/`onResize` entfallen.
- `script-src` in der CSP kommt ohne `'unsafe-inline'` aus.
- Mitgliederdaten und Datenstand werden in IndexedDB gespeichert.
- Start mit lokalem Stand, Hintergrundabgleich, verständliche Fehler.
- Dauerhafte Statusanzeige mit Quelle `Server` oder `lokal`.
- Der Grabber hält Laufbeginn und Abschlusszeitpunkt fest.
- Manueller Refresh-Button ohne HTTP-Cache.
- `401` und aktiver Logout löschen lokale Kartendaten.
- Bestehende Karte (Filter, Cluster, Popups, URL-Parameter, Radius, Hashtags,
  Reset, Logout) bleibt funktional unverändert.

## Nicht-Ziele

- PWA-Manifest, Icons, Service Worker und App-Shell-Cache (Phase 6/7).
- Persistenz von Zoom, Kartenausschnitt und Filtern (Phase 8).
- Standortfunktion (Phase 8).
- Umzug des `geo:`-Handlers (Phase 10).
- Änderungen an API-Abruf, Geocoding, Cache oder Datengrabber.

## Nutzerverhalten

### Start

1. Karte (Deutschland-Ansicht), Suchfeld und Buttons erscheinen sofort.
2. Ist ein lokaler Stand vorhanden, werden die Marker sofort angezeigt.
3. Die Statusanzeige zeigt zunächst `lokal` und wechselt nach erfolgreichem
   Serverabgleich auf `Server`, wenn Daten vom Server geladen oder bestätigt
   wurden.
4. Ohne lokalen Stand erscheint ein Hinweis `Kartendaten werden geladen …`.
5. Schlägt der erste Abruf ohne lokalen Stand fehl, erscheint eine verständliche
   Meldung mit „Erneut versuchen“.

### Statusanzeige

- Dauerhaft sichtbar, dezent, unten links als kleine halbtransparente Leiste.
- Format: `Datenstand: 06.11.2026, 03:33 · Server` bzw. `· lokal`.
- Quelle:
  - `Server`: Daten wurden in dieser Sitzung vom Server geladen oder per
    bedingtem Request (`304`) als aktuell bestätigt.
  - `lokal`: Daten stammen aus IndexedDB, weil noch kein Serverabgleich
    erfolgreich war, das Gerät offline ist oder der Abgleich fehlschlug.
  - Stimmt der Serverstand mit dem lokalen Stand überein, wird trotzdem ein
    bedingter Mitglieder-Request ausgeführt. Ein `304` bestätigt die Daten und
    setzt die Quelle auf `Server`, ohne die Datei erneut zu übertragen.
- Fehlgeschlagener Hintergrundabgleich bei vorhandenen lokalen Daten:
  `· lokal (Aktualisierung fehlgeschlagen)`.
- Datenstand älter als 48 Stunden: zusätzliche Warnfarbe und Text
  `älter als 48 h`.
- Ohne Daten ist die Statusanzeige ausgeblendet.

### Meldungen

- Eine kleine Meldungsleiste oben mittig zeigt `loading`, `error` und kurze
  Erfolgsmeldungen.
- Fehlertexte sind verständlich und ohne technische Details.
- Bei vorhandenen lokalen Daten blockiert ein Fehler die Karte nicht.

### Manueller Refresh

- Dritter Button `Kartendaten aktualisieren` in `#action_buttons`.
- Während des Ladens deaktiviert und als `lädt …` gekennzeichnet.
- Lädt `data-status.json` und `vmforum_members.json` mit `cache: 'no-store'`
  und ohne bedingte Header.
- Erfolg: Marker und Hashtag-Liste aktualisieren, Status `Server`, kurze Meldung
  `Kartendaten aktualisiert.`
- Fehler: bisherige Daten bleiben sichtbar, Status
  `lokal (Aktualisierung fehlgeschlagen)`, verständliche Fehlermeldung.

### `401`

- Lokale Kartendaten und Datenstand aus IndexedDB löschen.
- Weiterleitung auf `/login?next=…` mit aktuellem Pfad und Query.

### Logout

- Der bestehende `Abmelden`-Button löscht vor dem `POST /logout` die lokalen
  Kartendaten und den Datenstand aus IndexedDB.
- Danach wie bisher Weiterleitung auf `/login`.

## Speicherung

- IndexedDB-Datenbank `vmkarte`, Version 1, Object Store `kv` (Key-Value).
- Schlüssel:
  - `members` – Array der Mitglieder
  - `status` – `{ generatedAt, memberCount, source, savedAt }`
  - `etag` – ETag der zuletzt geladenen `vmforum_members.json`
  - `lastModified` – Last-Modified der zuletzt geladenen Datei
- Lesen validiert das Schema. Gültige `members` sind auch ohne gültigen
  `status` nutzbar; die Statusanzeige zeigt dann `Datenstand: unbekannt · lokal`
  und der Hintergrundabgleich läuft weiter. Ungültige `members` gelten wie
  „kein lokaler Stand“.
- Ist IndexedDB nicht verfügbar, wird nur im Speicher gearbeitet; die Karte
  bleibt funktionsfähig, im Konsolen-Log erscheint eine Warnung.

## Grabber-Zeitstempel

Phase 4 schreibt bereits `generatedAt` in `data-status.json`. Das ist der
Zeitpunkt, zu dem der Lauf die Kartendaten und den Status geschrieben hat, und
damit die Referenz für Datenstand und Alterswarnung im Frontend.

Ergänzend hält der Grabber den Laufbeginn fest:

```json
{
  "runStartedAt": "2026-11-06T03:33:00+01:00",
  "generatedAt": "2026-11-06T03:41:12+01:00",
  "memberCount": 3275
}
```

- `runStartedAt` wird am Anfang von `main()` ermittelt.
- `generatedAt` bleibt der Abschlusszeitpunkt nach dem Schreiben der Daten.
- Das Frontend verwendet `generatedAt` für Anzeige und 48-h-Warnung.
- `runStartedAt` steht zusätzlich im Tooltip der Statusanzeige und dient der
  Diagnose langer Läufe.
- Fehlt `runStartedAt` (ältere Datei), wird es ignoriert; das Frontend bleibt
  abwärtskompatibel.

## Datenabruf

### Hintergrundabgleich

1. `GET /shared/data-status.json` mit `cache: 'no-store'`.
2. Status validieren: Objekt, `generatedAt` parsebar, `memberCount` ganzzahlig.
3. `vmforum_members.json` laden, auch wenn der Serverstand gleich aussieht.
4. Bei vorhandenem ETag `If-None-Match` senden, sonst ohne bedingte Header.
5. `304`: lokale Daten behalten, Status auf `Server` setzen.
6. `200`: JSON validieren, speichern, Marker und Hashtags aktualisieren,
   Status `Server`.
7. Netzwerk-/Serverfehler: lokalen Stand behalten, Status
   `lokal (Aktualisierung fehlgeschlagen)`; ohne lokalen Stand Meldung zeigen.
8. `401`: lokale Daten löschen und auf `/login` weiterleiten.

Fällt nur `data-status.json` aus, wird ersatzweise direkt
`vmforum_members.json` per ETag geprüft. Der Datenstand wird dann aus dem
gespeicherten Status, sonst aus `Last-Modified` der Mitgliederdatei und
letztlich aus dem Abrufzeitpunkt abgeleitet.

### Validierung

- `data-status.json`: `generatedAt` per `Date.parse` gültig, `memberCount`
  nicht-negative Ganzzahl; `runStartedAt` optional und, falls vorhanden,
  parsebar.
- `vmforum_members.json`: Top-Level-Array. Jeder Eintrag braucht `id`, `name`
  sowie endliche `lat`/`lon`. Ungültige Einträge werden mit Konsolenwarnung
  übersprungen; bleibt kein gültiger Eintrag übrig, gilt die Datei als
  ungültig.

### ETag / Last-Modified

- ETag und Last-Modified werden aus den Antwortheadern gespeichert.
- Der ETag wird für bedingte Hintergrundabfragen verwendet.
- Der manuelle Refresh verwendet bewusst keine bedingten Header.

## Dateien

- `docker/webserver/www_data/karte.html` – App-Shell
- `docker/webserver/www_data/css/app.css` – ausgelagerte Styles
- `docker/webserver/www_data/js/app.js` – Karte, Filter, Popups, UI-Verdrahtung
- `docker/webserver/www_data/js/storage.js` – IndexedDB
- `docker/webserver/www_data/js/data.js` – Validierung, Statusvergleich,
  Zeitformatierung, Fetch-Helfer
- `docker/webserver/www_data/js/status-ui.js` – Status- und Meldungsleiste
- `docker/webserver/www_data/package.json` – `"type": "module"` für native
  ES-Module und Node-Tests
- `docker/webserver/default.conf` – `location` für `/js/` und `/css/`
- `docker/webserver/security-headers.conf` – `script-src` ohne `'unsafe-inline'`
- `src/data_grabber/libs/data_status_lib.py` – `runStartedAt` ergänzen
- `src/data_grabber/tests/test_data_status.py` – Tests für `runStartedAt`
- `tests/frontend/` – Node-Tests für reine Funktionen

## Technische Entscheidungen

- Native ES-Module ohne Build-Schritt.
- Die Karte bleibt eine klassische Leaflet/MarkerCluster-Seite; die Bibliotheken
  werden weiterhin als globale Skripte vor `app.js` geladen.
- `style-src 'unsafe-inline'` bleibt vorerst erlaubt, weil Leaflet Inline-Stile
  setzt. Nur `script-src` wird verschärft.
- Die Statusleiste sitzt unten links; die Leaflet-Attribution bleibt unten
  rechts.
- 48 Stunden ist die Warnschwelle für alte Daten.
- Für die Node-Tests wird ausschließlich der eingebaute Test-Runner verwendet;
  es kommt keine Playwright-/Puppeteer-Abhängigkeit ins Repository. Der
  Headless-Browsertest bleibt eine lokale, dokumentierte Verifikation mit einem
  vorhandenen Chrome/Edge.
- Logout löscht lokale Kartendaten bereits in Phase 5, weil das eine
  Anforderung aus `requirements.md` ist.

## Verifikation

- `node --check` für alle JS-Dateien.
- `node --test tests/frontend` für Validierung, Statusvergleich und
  Zeitformatierung.
- Headless-Browser-Test mit lokalem Static-Server (lokales Chrome/Edge, keine
  neue Testabhängigkeit):
  - ohne lokalen Stand: Laden → Serverdaten
  - mit lokalem Stand: sofortige Anzeige → Serverabgleich
  - Abgleichfehler: lokale Karte bleibt sichtbar, Status zeigt den Fehler
  - `401`: IndexedDB geleert, Weiterleitung auf `/login`
  - Logout: IndexedDB geleert, Weiterleitung auf `/login`
  - Filter, URL-Parameter, Popups und Reset funktionieren weiterhin
- `nginx -t`.
- CSP enthält kein `script-src 'unsafe-inline'` mehr.
