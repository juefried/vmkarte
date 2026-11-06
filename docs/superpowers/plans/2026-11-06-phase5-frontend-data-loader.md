# Phase 5 – Frontend-Datenloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Karte startet sofort mit lokal gespeicherten Daten, gleicht im Hintergrund mit dem Server ab, zeigt dauerhaft und dezent den Datenstand inklusive Quelle `Server`/`lokal` und erlaubt einen manuellen Refresh.

**Architecture:** `karte.html` wird App-Shell. CSS und JavaScript werden in `css/app.css` und native ES-Module unter `js/` ausgelagert. `storage.js` kapselt IndexedDB, `data.js` enthält reine Validierungs-/Formatierungsfunktionen, `status-ui.js` die Status- und Meldungsleiste, `app.js` die Karte und den Datenabruf. Der Grabber schreibt zusätzlich `runStartedAt`; das Frontend nutzt `generatedAt` für die Alterung.

**Tech Stack:** Statisches HTML, CSS, native ES-Module, Leaflet + MarkerCluster, IndexedDB, nginx, Python-Unittest, Node `node:test` (eingebaut).

**Spec:** `docs/superpowers/specs/2026-11-06-phase5-frontend-data-loader-design.md`

## Global Constraints

- Keine Zugangsdaten, Hashes oder Schlüssel im Client oder Repository.
- `local/ai/` bleibt untracked und wird nicht mitcommittet.
- Keine Änderungen an API-Abruf, Geocoding, Cache oder `vmforum_members.json`.
- `members.json` bleibt Debug-Datei außerhalb des Web-Roots.
- Bestehende Kartenfunktionen (Filter, Cluster, Popups, URL-Parameter, Radius, Hashtags, Reset, Logout) bleiben erhalten.
- Keine neue Frontend-Abhängigkeit; kein Bundler, kein Build-Schritt.
- `script-src` der CSP enthält am Ende kein `'unsafe-inline'`.
- `style-src 'unsafe-inline'` bleibt für Leaflet erlaubt.
- Datenstand ist dauerhaft sichtbar und unterscheidet `Server` von `lokal`.
- Warnschwelle für alte Daten: 48 Stunden.
- Keine aggressiven Login-/Rate-Limit-Tests auf dem Server (fail2ban).

## Branch

Vor Task 1:

```bash
git switch release/3.0-pwa
git pull --ff-only
git switch -c feature/phase5-data-loader
```

Design- und Plandokument werden auf diesem Branch mitcommittet.

## Review Focus

1. **Session läuft während der Nutzung ab (`401`):** lokale Daten müssen gelöscht werden und die Weiterleitung auf `/login` muss auch aus dem Hintergrundabgleich heraus funktionieren.
2. **Offline oder Server nicht erreichbar:** vorhandene lokale Marker bleiben sichtbar; die Statusanzeige zeigt `lokal (Aktualisierung fehlgeschlagen)` statt einer leeren Karte.
3. **Beschädigtes oder abgeschnittenes JSON:** `data-status.json` und `vmforum_members.json` dürfen keinen unbehandelten Fehler auslösen; bei vorhandenen lokalen Daten wird weitergearbeitet.
4. **IndexedDB nicht verfügbar oder Quota-Fehler:** die Karte funktioniert weiter, ohne unhandled rejection; ein Serverabruf bleibt möglich.
5. **Alte oder undatierte Daten:** mehr als 48 Stunden alte Daten werden gewarnt; fehlt `generatedAt`, erscheint `Datenstand: unbekannt · lokal`, nicht ein falsches frisches Datum.

---

### Task 1: Grabber-Laufzeit festhalten

**Files:**
- Modify: `src/data_grabber/libs/data_status_lib.py`
- Modify: `src/data_grabber/data_grabber.py`
- Test: `src/data_grabber/tests/test_data_status.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `build_data_status(member_count, generated_at=None, run_started_at=None) -> dict`
  - `write_data_status(path, member_count, generated_at=None, run_started_at=None) -> None`
  - `data-status.json` enthält bei neuen Läufen `runStartedAt`, `generatedAt`, `memberCount`.

- [ ] **Step 1: Failing Tests ergänzen**

In `src/data_grabber/tests/test_data_status.py` ergänzen:

```python
def test_includes_run_started_at_when_given(self):
    generated_at = datetime(2026, 11, 6, 3, 41, 12, tzinfo=timezone.utc)
    run_started_at = datetime(2026, 11, 6, 3, 33, 0, tzinfo=timezone.utc)
    status = build_data_status(3167, generated_at, run_started_at)
    self.assertEqual(status['runStartedAt'], '2026-11-06T03:33:00+00:00')
    self.assertEqual(status['generatedAt'], '2026-11-06T03:41:12+00:00')

def test_omits_run_started_at_when_not_given(self):
    status = build_data_status(1)
    self.assertNotIn('runStartedAt', status)

def test_writes_run_started_at(self):
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / 'data-status.json'
        generated_at = datetime(2026, 11, 6, 3, 41, 12, tzinfo=timezone.utc)
        run_started_at = datetime(2026, 11, 6, 3, 33, 0, tzinfo=timezone.utc)
        write_data_status(path, 2, generated_at, run_started_at)
        with path.open(encoding='utf-8') as status_file:
            self.assertEqual(json.load(status_file)['runStartedAt'], '2026-11-06T03:33:00+00:00')
```

- [ ] **Step 2: Tests laufen lassen und Fehler bestätigen**

Run: `python -m unittest discover -s src/data_grabber/tests -p "test_*.py" -v`  
Expected: Die neuen Tests scheitern mit `TypeError`/fehlendem `runStartedAt`.

- [ ] **Step 3: `data_status_lib.py` erweitern**

`build_data_status` und `write_data_status` erhalten den optionalen Parameter
`run_started_at=None`. Ist er gesetzt, wird `runStartedAt` mit
`run_started_at.isoformat(timespec='seconds')` aufgenommen; sonst wird das Feld
weggelassen. `write_data_status` reicht den Parameter an `build_data_status`
weiter.

- [ ] **Step 4: `data_grabber.py` erweitern**

`from datetime import datetime` ergänzen. Am Anfang von `main()` nach dem Parsen
der Argumente:

```python
run_started_at = datetime.now().astimezone()
```

Beim Status-Schreiben:

```python
write_data_status(DATA_STATUS_JSON_PATH, len(vmforum_members), run_started_at=run_started_at)
```

- [ ] **Step 5: Tests laufen lassen**

Run: `python -m unittest discover -s src/data_grabber/tests -p "test_*.py" -v`  
Expected: alle Tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/data_grabber/libs/data_status_lib.py src/data_grabber/data_grabber.py src/data_grabber/tests/test_data_status.py
git commit -m "feat(data-grabber): record run start time in data status"
```

---

### Task 2: App-Shell, CSS und JavaScript auslagern

**Files:**
- Modify: `docker/webserver/www_data/karte.html`
- Create: `docker/webserver/www_data/css/app.css`
- Create: `docker/webserver/www_data/js/app.js`
- Create: `docker/webserver/www_data/package.json`
- Modify: `docker/webserver/default.conf`
- Modify: `docker/webserver/security-headers.conf`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `karte.html` lädt `css/app.css`, Leaflet, MarkerCluster und
    `<script type="module" src="js/app.js"></script>`.
  - `js/app.js` definiert `create_map()` und ruft sie nach `DOMContentLoaded`
    auf; `resize_map_to_full_window()` hängt an `resize`.
  - `package.json` deklariert `{"private": true, "type": "module"}`.
  - nginx liefert `/css/` und `/js/`; CSP `script-src 'self'`.

- [ ] **Step 1: `css/app.css` anlegen**

Den Inhalt des bisherigen `<style>`-Blocks aus `karte.html` (Zeilen 14–44)
unverändert in `css/app.css` übernehmen.

- [ ] **Step 2: `js/app.js` anlegen**

Den Inhalt des bisherigen Inline-`<script>`-Blocks (Zeilen 49–404) übernehmen.
Folgende Anpassungen:

- `var`/globale Variablen beibehalten, solange sie zum bestehenden Verhalten
  gehören.
- `body onLoad="create_map();"` ersetzen durch:
  `document.addEventListener('DOMContentLoaded', create_map);`
- `body onResize="resize_map_to_full_window(); if (map) map.invalidateSize();"`
  ersetzen durch einen `window.addEventListener('resize', ...)`-Listener mit
  identischem Verhalten.
- Keine Inline-Event-Handler im HTML zurücklassen.

- [ ] **Step 3: `karte.html` auf App-Shell umbauen**

- `<style>`-Block entfernen und `<link rel="stylesheet" href="css/app.css" />`
  ergänzen.
- Inline-`<script>`-Block entfernen.
- Vor `app.js` weiterhin Leaflet und MarkerCluster laden.
- `<script type="module" src="js/app.js"></script>` vor `</body>` einfügen.
- `onLoad`/`onResize` aus `<body>` entfernen.
- Die bestehenden IDs (`map`, `search_controls`, `form_search`, `form_select`,
  `tags`, `reset_button`, `logout_button`) unverändert lassen.

- [ ] **Step 4: `package.json` anlegen**

```json
{
  "private": true,
  "type": "module"
}
```

- [ ] **Step 5: nginx anpassen**

In `docker/webserver/default.conf` die exakten Locations `/app.css` und
`/app.js` entfernen und ergänzen:

```nginx
location ^~ /css/ {
    try_files $uri =404;
    expires 1h;
}

location ^~ /js/ {
    try_files $uri =404;
    expires 1h;
}
```

In `docker/webserver/security-headers.conf` `script-src 'self' 'unsafe-inline'`
durch `script-src 'self'` ersetzen. `style-src 'unsafe-inline'` bleibt.

- [ ] **Step 6: Syntax und Funktion prüfen**

Run: `node --check docker/webserver/www_data/js/app.js`  
Expected: kein Fehler.

Run: `nginx -t` im lokalen nginx (falls vorhanden)  
Expected: `syntax is ok`.

Headless-Check mit lokalem Static-Server aus
`docker/webserver/www_data`:
- Karte rendert.
- Filter `alle` → `nur mit Velomobil` reduziert die Marker.
- Reset- und Abmelden-Button sind sichtbar.
- Keine CSP-Verstöße für Skripte in der Konsole.

- [ ] **Step 7: Commit**

```bash
git add docker/webserver/www_data/karte.html docker/webserver/www_data/css/app.css docker/webserver/www_data/js/app.js docker/webserver/www_data/package.json docker/webserver/default.conf docker/webserver/security-headers.conf
git commit -m "refactor(web): split map shell, styles and script"
```

---

### Task 3: Reine Datenfunktionen und Node-Tests

**Files:**
- Create: `docker/webserver/www_data/js/data.js`
- Create: `tests/frontend/data.test.js`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `export const STALE_AFTER_MS = 48 * 60 * 60 * 1000`
  - `export function parseDataStatus(raw) -> { generatedAt, runStartedAt, memberCount } | null`
  - `export function validateMembers(raw) -> { members, skipped } | null`
  - `export function isServerNewer(serverStatus, localStatus) -> boolean`
  - `export function formatStatusTimestamp(iso) -> string`
  - `export function isStale(generatedAt, now = Date.now()) -> boolean`
  - `export function deriveStatusFromLastModified(lastModified, memberCount) -> { generatedAt, runStartedAt: null, memberCount } | null`
  - `export function formatStatusText({ generatedAt, source, updateFailed, stale }) -> string`

- [ ] **Step 1: Failing Tests schreiben**

In `tests/frontend/data.test.js` mit `node:test` und `node:assert/strict`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parseDataStatus,
  validateMembers,
  isServerNewer,
  formatStatusTimestamp,
  isStale,
  deriveStatusFromLastModified,
  formatStatusText,
} from '../../docker/webserver/www_data/js/data.js';

test('parseDataStatus accepts valid status', () => {
  assert.deepEqual(
    parseDataStatus({ generatedAt: '2026-11-06T03:33:00+01:00', memberCount: 3167 }),
    { generatedAt: '2026-11-06T03:33:00+01:00', runStartedAt: null, memberCount: 3167 },
  );
});

test('parseDataStatus rejects invalid timestamp and member count', () => {
  assert.equal(parseDataStatus({ generatedAt: 'nope', memberCount: 1 }), null);
  assert.equal(parseDataStatus({ generatedAt: '2026-11-06T03:33:00+01:00', memberCount: -1 }), null);
  assert.equal(parseDataStatus(null), null);
});

test('validateMembers skips invalid entries', () => {
  const result = validateMembers([
    { id: '1', name: 'A', lat: '50.0', lon: '10.0' },
    { id: '2', name: 'B', lat: 'nope', lon: '10.0' },
  ]);
  assert.equal(result.members.length, 1);
  assert.equal(result.skipped, 1);
});

test('validateMembers rejects non-arrays and empty result', () => {
  assert.equal(validateMembers({}), null);
  assert.equal(validateMembers([{ id: '1' }]), null);
});

test('isServerNewer compares timestamps and handles missing local status', () => {
  assert.equal(isServerNewer({ generatedAt: '2026-11-06T04:00:00Z' }, null), true);
  assert.equal(isServerNewer({ generatedAt: '2026-11-06T04:00:00Z' }, { generatedAt: '2026-11-06T03:00:00Z' }), true);
  assert.equal(isServerNewer({ generatedAt: '2026-11-06T03:00:00Z' }, { generatedAt: '2026-11-06T03:00:00Z' }), false);
});

test('formatStatusTimestamp formats German local time', () => {
  assert.match(formatStatusTimestamp('2026-11-06T03:33:00+01:00'), /^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}$/);
});

test('isStale uses the 48 hour threshold', () => {
  const now = Date.parse('2026-11-08T03:33:00Z');
  assert.equal(isStale('2026-11-06T03:33:00Z', now), false);
  assert.equal(isStale('2026-11-06T03:32:59Z', now), true);
});

test('deriveStatusFromLastModified parses HTTP dates', () => {
  const status = deriveStatusFromLastModified('Fri, 06 Nov 2026 02:33:00 GMT', 7);
  assert.equal(status.generatedAt, '2026-11-06T02:33:00.000Z');
  assert.equal(status.memberCount, 7);
  assert.equal(deriveStatusFromLastModified('nope', 7), null);
});

test('formatStatusText marks source and stale state', () => {
  assert.equal(formatStatusText({ generatedAt: '2026-11-06T03:33:00+01:00', source: 'server', updateFailed: false, stale: false }), 'Datenstand: 06.11.2026, 03:33 · Server');
  assert.match(formatStatusText({ generatedAt: '2026-11-06T03:33:00+01:00', source: 'local', updateFailed: true, stale: true }), /lokal \(Aktualisierung fehlgeschlagen\).*älter als 48 h/);
  assert.equal(formatStatusText({ generatedAt: null, source: 'local', updateFailed: false, stale: false }), 'Datenstand: unbekannt · lokal');
});
```

- [ ] **Step 2: Tests laufen lassen und Fehler bestätigen**

Run: `node --test tests/frontend/data.test.js`  
Expected: FAIL, weil `js/data.js` fehlt.

- [ ] **Step 3: `js/data.js` implementieren**

Implementierung mit den oben fixierten Signaturen. Genauigkeit:

- `parseDataStatus` prüft `generatedAt` per `Date.parse`, `memberCount` als
  nicht-negative Ganzzahl; `runStartedAt` optional und parsebar.
- `validateMembers` verlangt Array; `id`/`name` als Strings, `lat`/`lon`
  endlich nach `Number(...)`; ungültige Einträge zählen als `skipped`.
- `isServerNewer` vergleicht `Date.parse`; fehlender lokaler Status ⇒ `true`.
- `formatStatusTimestamp` nutzt
  `Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })`,
  damit das Jahr vierstellig ist.
- `formatStatusText` erzeugt exakt:
  - `Datenstand: <zeit> · Server`
  - `Datenstand: <zeit> · lokal`
  - `Datenstand: unbekannt · lokal`
  - bei `updateFailed`: `· lokal (Aktualisierung fehlgeschlagen)`
  - bei `stale`: zusätzlich ` · älter als 48 h`
- `deriveStatusFromLastModified` nutzt `new Date(lastModified)`; ungültig ⇒
  `null`; `generatedAt` als `toISOString()`.

- [ ] **Step 4: Tests laufen lassen**

Run: `node --test tests/frontend/data.test.js`  
Expected: alle Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add docker/webserver/www_data/js/data.js tests/frontend/data.test.js
git commit -m "feat(web): add data validation and status helpers"
```

---

### Task 4: IndexedDB, Status-UI und Start mit lokalem Stand

**Files:**
- Create: `docker/webserver/www_data/js/storage.js`
- Create: `docker/webserver/www_data/js/status-ui.js`
- Modify: `docker/webserver/www_data/js/app.js`
- Modify: `docker/webserver/www_data/karte.html`
- Modify: `docker/webserver/www_data/css/app.css`

**Interfaces:**
- Consumes: `validateMembers`, `parseDataStatus`, `formatStatusText`,
  `formatStatusTimestamp`, `isStale` aus `data.js`.
- Produces:
  - `storage.js`: `readCache() -> Promise<{ members, status, etag, lastModified } | null>`,
    `writeCache({ members, status, etag, lastModified }) -> Promise<void>`,
    `clearCache() -> Promise<void>`.
  - `status-ui.js`: `createStatusUi({ statusElement, messageElement }) -> { setStatus, clearStatus, setMessage, clearMessage }`;
  `setStatus` setzt auch den `title` mit `runStartedAt`, falls vorhanden.
  - `app.js` zeigt beim Start zuerst lokale Marker und `lokal`; ohne Cache
    `Kartendaten werden geladen …`.

- [ ] **Step 1: `storage.js` implementieren**

IndexedDB `vmkarte`, Version 1, Store `kv`. `readCache` liest die Schlüssel
`members`, `status`, `etag`, `lastModified`; `members` wird mit
`validateMembers` geprüft, `status` mit `parseDataStatus`. Ungültige Werte
werden als `null` zurückgegeben. Ist IndexedDB nicht verfügbar, werden die
Funktionen mit einer Konsolenwarnung zu No-Ops (`readCache` ⇒ `null`).
`writeCache` schreibt alle vier Werte in einer Transaktion; `clearCache` leert
den Store.

- [ ] **Step 2: `status-ui.js` implementieren**

`createStatusUi` setzt `statusElement.textContent` über `formatStatusText`,
setzt/entfernt CSS-Klassen `status-server`, `status-local`, `status-warning` und
steuert die Meldungsleiste über `textContent`. `setMessage({ type, text, onRetry })`
darf einen Retry-Button erzeugen; `clearMessage()` entfernt ihn.

- [ ] **Step 3: App-Shell erweitern**

In `karte.html` vor `</body>`:

```html
<div id="data_status" class="data-status" aria-live="polite"></div>
<div id="data_message" class="data-message" hidden></div>
```

In `#action_buttons` einen dritten Button ergänzen:

```html
<button type="button" id="refresh_button" title="Kartendaten vom Server aktualisieren">Kartendaten aktualisieren</button>
```

In `css/app.css` die Statusleiste unten links, die Meldungsleiste oben mittig
und den Refresh-Button dezent gestalten; auf schmalen Viewports dürfen die
Buttons umbrechen.

- [ ] **Step 4: `app.js` auf lokalen Start umbauen**

- `import { readCache, writeCache, clearCache } from './storage.js';`
- `import { createStatusUi } from './status-ui.js';`
- `import { validateMembers, parseDataStatus, formatStatusText, formatStatusTimestamp, isStale } from './data.js';`
- `members` von Promise auf `let members = [];` umstellen.
- `create_map()` wird `async function init()`:
  1. `statusUi` mit den neuen Elementen erzeugen.
  2. `const cache = await readCache().catch(...)`.
  3. Karte und Controls wie bisher aufbauen.
  4. Bei `cache.members`: `members = cache.members`, `add_vmforum_members()`,
     `add_vmforum_tags()`, Status auf `lokal` setzen.
  5. Sonst Meldung `Kartendaten werden geladen …` anzeigen.
- `add_vmforum_tags()` leert `#tags` vor dem Neuaufbau.
- `logout()` ruft vor dem `POST /logout` `await clearCache()` auf.
- `window.addEventListener('resize', ...)` beibehalten.

- [ ] **Step 5: Syntax prüfen**

Run: `node --check docker/webserver/www_data/js/storage.js; node --check docker/webserver/www_data/js/status-ui.js; node --check docker/webserver/www_data/js/app.js`  
Expected: kein Fehler.

- [ ] **Step 6: Headless-Check mit lokalem Stand**

Temp-Kopie von `docker/webserver/www_data` erzeugen, dort eine Seed-Seite
ablegen, die `js/storage.js` importiert und Testmarker + Status schreibt, dann
`karte.html` laden. Prüfen:
- Marker sind sofort sichtbar.
- Status zeigt `Datenstand: … · lokal`.
- Keine Konsolenfehler.

- [ ] **Step 7: Commit**

```bash
git add docker/webserver/www_data/js/storage.js docker/webserver/www_data/js/status-ui.js docker/webserver/www_data/js/app.js docker/webserver/www_data/karte.html docker/webserver/www_data/css/app.css
git commit -m "feat(web): load cached map data and show local status"
```

---

### Task 5: Serverabgleich, ETag, manueller Refresh, 401 und Logout

**Files:**
- Modify: `docker/webserver/www_data/js/app.js`
- Modify: `docker/webserver/www_data/js/storage.js` (nur falls für ETag nötig)
- Test: `tests/frontend/data.test.js` (nur falls neue reine Funktionen)

**Interfaces:**
- Consumes: alle Interfaces aus Task 3 und 4.
- Produces:
  - `syncFromServer({ manual = false }) -> Promise<void>`
  - Hintergrundabgleich beim Start.
  - Refresh-Button ruft `syncFromServer({ manual: true })` auf.
  - `401` löscht Cache und leitet auf `/login?next=…` weiter.

- [ ] **Step 1: Fetch-Helfer und Ablauf implementieren**

In `app.js`:

- `const DATA_STATUS_URL = 'shared/data-status.json';`
- `const MEMBERS_URL = 'shared/vmforum_members.json';`
- `async function fetchStatus()`: `fetch(DATA_STATUS_URL, { cache: 'no-store', credentials: 'same-origin' })`;
  `401` ⇒ `handleUnauthorized()`; sonst JSON und `parseDataStatus`.
- `async function syncFromServer({ manual = false } = {})`:
  1. Doppelaufrufe über `updateInProgress` verhindern.
  2. Status laden; Fehler tolerieren.
  3. `vmforum_members.json` laden:
     - bei `manual` ohne bedingte Header, `cache: 'no-store'`;
     - sonst `If-None-Match` mit gespeichertem ETag, falls vorhanden.
  4. `304` ⇒ Status `Server`, gespeicherten Status mit dem Serverstatus
     aktualisieren, keine Änderung an den Mitgliederdaten.
  5. `200` ⇒ `validateMembers`; bei Erfolg `writeCache` inklusive
     `response.headers.get('ETag')` und `response.headers.get('Last-Modified')`,
     Marker/Hashtags aktualisieren; Status `Server`.
  6. `401` ⇒ `handleUnauthorized()`.
  7. Andere Fehler ⇒ bei vorhandenen Daten Status
     `lokal (Aktualisierung fehlgeschlagen)`, sonst Fehlermeldung mit Retry.
  8. Fehlt ein gültiger `data-status.json`, wird der Status aus
     `Last-Modified` (`deriveStatusFromLastModified`) oder dem Abrufzeitpunkt
     abgeleitet.
- `handleUnauthorized()`: `await clearCache()`, dann
  `window.location.assign('/login?next=' + encodeURIComponent(location.pathname + location.search))`.
- `logout()`: `await clearCache()` vor dem `POST /logout`, danach `/login`.

- [ ] **Step 2: Refresh-Button verdrahten**

`refresh_button` deaktivieren, Text auf `lädt …` setzen, nach Abschluss
wiederherstellen. Erfolg: kurze Meldung `Kartendaten aktualisiert.` (nach 3 s
ausblenden). Fehler: Meldung mit Retry.

- [ ] **Step 3: Statusanzeige bei jedem Zustand aktualisieren**

- Start mit lokalem Stand: `lokal`.
- Erfolgreicher Serverabgleich/`304`: `Server`.
- Fehlgeschlagener Abgleich mit lokalen Daten:
  `lokal (Aktualisierung fehlgeschlagen)`.
- Kein lokaler Stand und Fehler: Status ausblenden, Meldung zeigen.
- `isStale(generatedAt)` ⇒ Warnklasse und `älter als 48 h`.
- `runStartedAt` im `title` der Statusanzeige anzeigen, wenn vorhanden.

- [ ] **Step 4: Syntax und reine Tests prüfen**

Run: `node --check docker/webserver/www_data/js/app.js`  
Run: `node --test tests/frontend/data.test.js`  
Expected: PASS.

- [ ] **Step 5: Headless-Integration prüfen**

Mit lokalem Static-Server:
- ohne Cache: `Kartendaten werden geladen …` → Marker → `· Server`.
- mit Cache: sofortige Marker → `· lokal` → nach Abgleich `· Server`.
- Serverantwort unterbrochen: Marker bleiben, Status
  `lokal (Aktualisierung fehlgeschlagen)`.
- `401` simulieren: IndexedDB leer, Weiterleitung auf `/login`.
- Refresh-Button: Erfolg und Fehlerzustand.
- Filter, URL-Parameter, Popups und Reset funktionieren unverändert.

- [ ] **Step 6: Commit**

```bash
git add docker/webserver/www_data/js/app.js
git commit -m "feat(web): sync map data with server and support manual refresh"
```

---

### Task 6: Gesamtverifikation, Dokumentation und Merge

**Files:**
- Modify: `docs/upgrade-3.0-auth.md` (nur falls Deployment-Hinweise nötig)
- Modify: `local/ai/phases.md` (nicht committen)
- Modify: `local/ai/changelog.md` (nicht committen)
- Modify: `local/ai/README.md` (nicht committen)

- [ ] **Step 1: Vollständige Tests**

Run:
```powershell
python -m unittest discover -s src/data_grabber/tests -p "test_*.py"
node --test tests/frontend
node --check docker/webserver/www_data/js/app.js
node --check docker/webserver/www_data/js/data.js
node --check docker/webserver/www_data/js/storage.js
node --check docker/webserver/www_data/js/status-ui.js
```
Expected: alles PASS/OK.

- [ ] **Step 2: nginx und CSP prüfen**

Run: `nginx -t`  
Expected: `syntax is ok`.

Prüfen: `security-headers.conf` enthält
`script-src 'self'` ohne `'unsafe-inline'`.

- [ ] **Step 3: Headless-Abnahme**

Die fünf Review-Focus-Fälle aus dem Kopf dieser Datei einzeln prüfen und die
Ergebnisse notieren.

- [ ] **Step 4: Doku aktualisieren**

- In `local/ai/phases.md` Phase 5 abhaken.
- In `local/ai/changelog.md` einen Eintrag mit Datum, Änderungen,
  Verifikationsergebnissen und Commit-Hashes ergänzen.
- In `local/ai/README.md` den Stand auf Phase 5 aktualisieren.
- Falls nötig, `docs/upgrade-3.0-auth.md` um die neuen statischen Pfade
  `/js/` und `/css/` ergänzen.
- `local/ai/` bleibt untracked.

- [ ] **Step 5: Commit, Merge, Push**

```bash
git status --short
git add docker/webserver/www_data/karte.html docker/webserver/www_data/css/app.css docker/webserver/www_data/js docker/webserver/www_data/package.json docker/webserver/default.conf docker/webserver/security-headers.conf tests/frontend docs/superpowers/specs docs/superpowers/plans
git commit -m "docs(web): document phase 5 data loader"
git switch release/3.0-pwa
git merge --no-ff feature/phase5-data-loader -m "Merge branch 'feature/phase5-data-loader' into release/3.0-pwa"
git push origin release/3.0-pwa
```

Falls die Design-/Plandokumente bereits in Task 2–5 committet wurden, nur die
noch offenen Dateien stagen. `local/ai/` nicht stagen.
