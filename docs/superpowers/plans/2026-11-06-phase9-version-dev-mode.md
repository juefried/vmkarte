# Phase 9 – Version und Entwicklungsbetrieb

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die PWA erhält eine betriebsreife Versionierung mit Build-Datum, Update-Erkennung, bestätigtem Neuladen, Entwicklungsmodus mit Cache-Bypass sowie dokumentierter Cache-Löschung, Deployment und Rollback.

**Architecture:** Die Version steht als gepflegte `VERSION`-Datei im Web-Root und wird beim Docker-Build zusammen mit dem Build-Datum in `app-version.json` und `js/version.js` geschrieben. Die laufende App importiert `APP_VERSION` aus `js/version.js`, lädt beim Start `/app-version.json` ohne Cache und zeigt bei exakter Ungleichheit einen gemeinsamen Update-Hinweis. `?dev=1` aktiviert für die Tab-Session einen Cache-Bypass, der Service Worker abmeldet und `vmkarte-`-Caches löscht.

**Tech Stack:** Vanilla JavaScript (ES-Module), Service Worker/Cache Storage, IndexedDB (unverändert), Docker/nginx, Node-Testrunner, Headless Chrome/CDP.

**Spec:** `local/ai/requirements.md` (PWA, Version und Update, Betrieb), `local/ai/phases.md` (Phase 9), `docs/upgrade-3.0-auth.md`.

## Global Constraints

- Keine Zugangsdaten, Hashes oder Schlüssel einchecken.
- `config/.htpasswd` und `config/session_signing_key` bleiben außerhalb von Git.
- `members.json` bleibt Debug-Datei außerhalb des Web-Roots.
- `local/ai/` bleibt untracked und wird nicht committet.
- Bei Änderungen an `www_data`-App-Dateien `CACHE_NAME` von `vmkarte-shell-v5` auf `vmkarte-shell-v6` erhöhen.
- `/shared/`, `/login`, `/logout`, `/session-check` und `/_internal/session-check` bleiben network-only.
- `/app-version.json` wird nicht vom Service Worker gecacht.
- Neuladen erfolgt ausschließlich nach Bestätigung durch den Nutzer.
- Keine neuen statischen Verzeichnisse ohne nginx-`location`-Block; Phase 9 braucht keinen neuen Block.
- Die bestehende Phase-8-Funktionalität bleibt erhalten.

## Review Focus

- **Offline oder HTTP-Fehler bei `/app-version.json`:** darf keine Fehlermeldung und keinen Update-Hinweis erzeugen, die Karte muss normal weiterlaufen.
- **Gleiche Version:** darf keinen Hinweis erzeugen, auch nicht nach mehreren Starts.
- **Dev-Modus:** gilt nur für die aktuelle Tab-Session, `?dev=0` deaktiviert ihn, und ohne Parameter bleibt er aus.
- **Automatisches Neuladen:** darf nicht vorkommen; der Hinweis bleibt stehen, bis „Neu laden“ geklickt wird.
- **Build ohne ARG:** `docker compose build web` muss trotzdem die Version aus `VERSION` übernehmen, nicht `dev`.
- **Service-Worker-Cache:** `/app-version.json` darf nach einem Lauf nicht in einem `vmkarte-`-Cache liegen.

---

### Task 1: Versions-Hilfsfunktionen mit Tests

**Files:**
- Create: `docker/webserver/www_data/js/version-check.js`
- Test: `tests/frontend/version.test.js`

**Interfaces:**
- `export const DEV_MODE_KEY = 'vmkarte-dev-mode'`
- `export function parseAppVersion(value)` → `{ version: string, buildDate: string|null } | null`
- `export function isNewVersion(currentVersion, remoteVersion)` → `boolean`
- `export function resolveDevMode(search, stored)` → `{ enabled: boolean, persist: boolean, clear: boolean }`

**Semantik:**
- `parseAppVersion` akzeptiert nur Objekte mit nicht-leerem String `version`; `buildDate` wird getrimmt und ist sonst `null`.
- `isNewVersion` ist nur wahr, wenn beide Werte nicht-leere Strings sind und sich exakt unterscheiden. Kein SemVer-Parsing.
- `resolveDevMode('?dev=1', …)` → `{ enabled: true, persist: true, clear: false }`
- `resolveDevMode('?dev=0', …)` → `{ enabled: false, persist: false, clear: true }`
- Ohne `dev`-Parameter entscheidet `stored === '1'`; dann ist `persist` und `clear` jeweils `false`.

- [ ] **Step 1: Failing Tests schreiben**

`tests/frontend/version.test.js` mit `node:test` und `node:assert/strict` anlegen. Mindestens diese Fälle:

```js
test('parseAppVersion accepts version and build date', () => {
	assert.deepEqual(
		parseAppVersion({ version: ' 3.0.0 ', buildDate: ' 2026-11-06T10:00:00Z ' }),
		{ version: '3.0.0', buildDate: '2026-11-06T10:00:00Z' },
	);
});

test('parseAppVersion rejects missing or invalid version', () => {
	assert.equal(parseAppVersion(null), null);
	assert.equal(parseAppVersion({}), null);
	assert.equal(parseAppVersion({ version: '' }), null);
	assert.equal(parseAppVersion({ version: 3 }), null);
});

test('parseAppVersion treats missing build date as null', () => {
	assert.deepEqual(parseAppVersion({ version: '3.0.0' }), { version: '3.0.0', buildDate: null });
});

test('isNewVersion uses exact inequality', () => {
	assert.equal(isNewVersion('3.0.0', '3.0.0'), false);
	assert.equal(isNewVersion('3.0.0', '3.0.1'), true);
	assert.equal(isNewVersion('3.0.0', ''), false);
	assert.equal(isNewVersion(undefined, '3.0.1'), false);
});

test('resolveDevMode enables and persists with dev=1', () => {
	assert.deepEqual(resolveDevMode('?dev=1', null), { enabled: true, persist: true, clear: false });
});

test('resolveDevMode disables and clears with dev=0', () => {
	assert.deepEqual(resolveDevMode('?dev=0', '1'), { enabled: false, persist: false, clear: true });
});

test('resolveDevMode restores a stored tab session', () => {
	assert.deepEqual(resolveDevMode('', '1'), { enabled: true, persist: false, clear: false });
	assert.deepEqual(resolveDevMode('', null), { enabled: false, persist: false, clear: false });
});

test('resolveDevMode ignores non-boolean dev values', () => {
	assert.deepEqual(resolveDevMode('?dev=true', null), { enabled: false, persist: false, clear: false });
});
```

- [ ] **Step 2: Tests laufen lassen und Fehlschlag prüfen**

Run: `node --test tests/frontend/version.test.js`
Expected: FAIL, weil `version-check.js` noch nicht existiert.

- [ ] **Step 3: `version-check.js` implementieren**

Die drei Funktionen und `DEV_MODE_KEY` gemäß Interfaces implementieren. `URLSearchParams` verwenden; keine DOM-Abhängigkeit.

- [ ] **Step 4: Tests laufen lassen**

Run: `node --test tests/frontend/version.test.js`
Expected: alle Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add docker/webserver/www_data/js/version-check.js tests/frontend/version.test.js
git commit -m "feat(web): add version check helpers"
```

---

### Task 2: Build-Zeit-Version und Build-Datum

**Files:**
- Create: `docker/webserver/www_data/VERSION`
- Create: `docker/webserver/www_data/js/version.js`
- Create: `docker/webserver/www_data/app-version.json`
- Modify: `docker/webserver/Dockerfile`
- Modify: `docker-compose.yml.sample`

**Interfaces:**
- `VERSION` enthält genau eine Zeile `3.0.0` (ohne `v`-Präfix, ohne Whitespace).
- `js/version.js` ist ein ES-Modul mit `export const APP_VERSION = 'dev';` und `export const BUILD_DATE = null;` als lokale Fallback-Werte.
- `app-version.json` enthält lokal `{"version":"dev","buildDate":null}`.
- Das Dockerfile erzeugt beide Dateien aus `ARG APP_VERSION` und `ARG BUILD_DATE`; ohne ARG wird `APP_VERSION` aus `/www_data/VERSION` gelesen und `BUILD_DATE` auf die aktuelle UTC-Zeit gesetzt.

- [ ] **Step 1: Fallback-Dateien anlegen**

`VERSION` mit `3.0.0` anlegen. `js/version.js` und `app-version.json` mit den Dev-Fallbacks anlegen. `node --check docker/webserver/www_data/js/version.js` muss erfolgreich sein.

- [ ] **Step 2: Dockerfile erweitern**

Vor der finalen `chown`-Zeile, nach `COPY www_data /www_data`, einfügen:

```dockerfile
ARG APP_VERSION=
ARG BUILD_DATE=

RUN set -e; \
    if [ -z "$APP_VERSION" ]; then APP_VERSION=$(cat /www_data/VERSION); fi; \
    BUILD_DATE="${BUILD_DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"; \
    printf '{"version":"%s","buildDate":"%s"}\n' "$APP_VERSION" "$BUILD_DATE" > /www_data/app-version.json; \
    printf 'export const APP_VERSION = "%s";\nexport const BUILD_DATE = "%s";\n' "$APP_VERSION" "$BUILD_DATE" > /www_data/js/version.js
```

- [ ] **Step 3: Compose-Sample erweitern**

Im `web`-Service `build.args` ergänzen:

```yaml
    build:
      context: docker/webserver
      args:
        APP_VERSION: ${APP_VERSION:-}
        BUILD_DATE: ${BUILD_DATE:-}
```

Damit funktioniert `docker compose build web` ohne zusätzliche Variablen und liest die Version aus `VERSION`. Ein explizites `APP_VERSION` überschreibt sie.

- [ ] **Step 4: Generierung ohne Docker prüfen**

Simuliere den Shell-Block lokal (PowerShell-Alternative) oder prüfe per Review, dass die Dateien nach dem Muster erzeugt werden. Zusätzlich:

Run: `node --check docker/webserver/www_data/js/version.js`
Expected: Exit 0.

- [ ] **Step 5: Commit**

```bash
git add docker/webserver/www_data/VERSION docker/webserver/www_data/js/version.js docker/webserver/www_data/app-version.json docker/webserver/Dockerfile docker-compose.yml.sample
git commit -m "build(web): generate app version and build date"
```

---

### Task 3: Update-Erkennung und gemeinsamer Hinweis

**Files:**
- Modify: `docker/webserver/www_data/js/app.js`

**Interfaces:**
- `const APP_VERSION_URL = 'app-version.json';`
- `function show_update_message()` zeigt genau einen Hinweis mit Text „Eine neue Version ist verfügbar.“, Aktion „Neu laden“ und `autoHideMs: 0`.
- `async function request_update_reload()` sucht einen wartenden Service Worker; wenn vorhanden, `SKIP_WAITING` und Reload nach `controllerchange`, sonst normales `window.location.reload()`.
- `async function find_waiting_worker(timeoutMs = 3000)` ruft `registration.update()` auf und pollt bis zu 3 s auf `registration.waiting`.
- `async function check_app_version()` lädt `/app-version.json` mit `cache: 'no-store'`, validiert mit `parseAppVersion` und zeigt bei `isNewVersion(APP_VERSION, remote.version)` den Hinweis. Fehler werden nur mit `console.warn` behandelt.
- `register_service_worker()` verwendet für `waiting` und `updatefound` nur noch `show_update_message()`.

- [ ] **Step 1: Importe ergänzen**

```js
import { APP_VERSION } from './version.js';
import { parseAppVersion, isNewVersion } from './version-check.js';
```

- [ ] **Step 2: Update-Hinweis vereinheitlichen**

`show_update_message(registration)` durch `show_update_message()` ersetzen und die Reload-Logik in `find_waiting_worker()` und `request_update_reload()` auslagern. Ein Modul-Flag `update_reload_pending` verhindert doppelte Reload-Listener.

- [ ] **Step 3: Versionsprüfung ergänzen**

`check_app_version()` wie oben implementieren. In `create_map()` nach `syncFromServer()` und zusammen mit der Service-Worker-Registrierung aufrufen. Die Prüfung läuft unabhängig davon, ob ein Service Worker unterstützt wird.

- [ ] **Step 4: Syntax prüfen**

Run: `node --check docker/webserver/www_data/js/app.js`
Expected: Exit 0.

- [ ] **Step 5: Commit**

```bash
git add docker/webserver/www_data/js/app.js
git commit -m "feat(web): detect app version updates"
```

---

### Task 4: Entwicklungsmodus und Service-Worker-Cache

**Files:**
- Modify: `docker/webserver/www_data/js/app.js`
- Modify: `docker/webserver/www_data/service-worker.js`

**Interfaces:**
- `CACHE_NAME = 'vmkarte-shell-v6'`
- `SHELL_URLS` enthält zusätzlich `/js/version.js` und `/js/version-check.js`.
- `NETWORK_ONLY_PATHS` enthält zusätzlich `/app-version.json`.
- `read_dev_mode()` liest `sessionStorage.getItem(DEV_MODE_KEY)` und fängt Fehler ab.
- `apply_dev_mode(devMode)` setzt bei `persist` den Wert `'1'` und entfernt ihn bei `clear`.
- In `create_map()`:

```js
const devMode = resolveDevMode(window.location.search, read_dev_mode());
apply_dev_mode(devMode);
```

- Bei `devMode.enabled`: `await clearAppCaches();` und Statusmeldung „Entwicklungsmodus aktiv: Service Worker und App-Caches sind deaktiviert.“; danach weder Service Worker registrieren noch Versionsprüfung starten.
- Ohne Dev-Modus: bestehende Registrierung plus `check_app_version()`.

- [ ] **Step 1: Service Worker anpassen**

`CACHE_NAME` auf `vmkarte-shell-v6` erhöhen, die beiden neuen JS-Dateien in `SHELL_URLS` aufnehmen und `/app-version.json` in `NETWORK_ONLY_PATHS` eintragen.

- [ ] **Step 2: Dev-Modus in `app.js` ergänzen**

`DEV_MODE_KEY` und `resolveDevMode` importieren, Helfer implementieren und den Branch am Ende von `create_map()` einbauen. `clearAppCaches()` wird wiederverwendet; IndexedDB bleibt erhalten, weil der Dev-Modus nur App-Caches betrifft.

- [ ] **Step 3: Syntax prüfen**

Run:
```
node --check docker/webserver/www_data/js/app.js
node --check docker/webserver/www_data/service-worker.js
```
Expected: beide Exit 0.

- [ ] **Step 4: Commit**

```bash
git add docker/webserver/www_data/js/app.js docker/webserver/www_data/service-worker.js
git commit -m "feat(web): add development cache bypass"
```

---

### Task 5: Phase-9-Browserregressionstest

**Files:**
- Create: `tests/browser/phase9-cdp.mjs`

**Interfaces:**
- Der Test übernimmt Server- und CDP-Harness aus `tests/browser/phase8-cdp.mjs`.
- Der lokale Server liefert `/app-version.json` aus einer veränderbaren Variable und `/js/version.js` von der Platte (Dev-Fallback).
- Der Test prüft die in „Review Focus“ genannten Punkte.

**Testschritte:**
1. Normaler Start mit `app-version.json` Version `dev`: kein Update-Hinweis, Karte lädt.
2. Warten, bis ein Service Worker registriert ist, und prüfen, dass `vmkarte-`-Caches existieren.
3. `/karte.html?dev=1`: Meldung „Entwicklungsmodus aktiv …“ sichtbar; nach kurzer Wartezeit `navigator.serviceWorker.getRegistrations()` leer und keine `vmkarte-`-Caches mehr.
4. `/karte.html?dev=0`: Dev-Modus deaktiviert, kein Dev-Hinweis; Service Worker registriert sich wieder.
5. Server liefert Version `9.9.9`: Update-Hinweis „Eine neue Version ist verfügbar.“ erscheint, Button „Neu laden“ vorhanden.
6. 1,5 s warten: die Seite wurde nicht automatisch neu geladen (Sentinel-Variable im `window` bleibt erhalten).
7. Server liefert HTTP 500 für `/app-version.json`: kein Update-Hinweis, keine sichtbare Fehlermeldung, Karte bleibt bedienbar.
8. Nach normalem Lauf prüfen: `/app-version.json` liegt in keinem `vmkarte-`-Cache.

- [ ] **Step 1: Test aus Phase 8 ableiten und die acht Prüfungen implementieren**

Die Leaflet-/CDP-Hilfsfunktionen und den statischen Dateiserver aus `phase8-cdp.mjs` übernehmen, aber nur die für Phase 9 nötigen Daten und Marker bereitstellen.

- [ ] **Step 2: Test laufen lassen**

Run: `node tests/browser/phase9-cdp.mjs`
Expected: alle PASS, Exit 0.

- [ ] **Step 3: Commit**

```bash
git add tests/browser/phase9-cdp.mjs
git commit -m "test(web): add phase 9 browser regression test"
```

---

### Task 6: Dokumentation und Phasenstand

**Files:**
- Modify: `docs/upgrade-3.0-auth.md`
- Modify: `DOKUMENTATION.md`
- Modify: `local/ai/phases.md`
- Modify: `local/ai/changelog.md`

**Doku-Inhalte für `docs/upgrade-3.0-auth.md`:**
- Neuer Abschnitt „Version und Update (Phase 9)“:
  - `VERSION` als Quelle, optional `APP_VERSION`/`BUILD_DATE` als Build-Args.
  - Format von `app-version.json`.
  - Exakter Versionsvergleich, Hinweis erst bei Ungleichheit.
  - Gemeinsamer Update-Hinweis; `SKIP_WAITING` nur bei wartendem Worker, sonst normales Reload.
  - Ohne `APP_VERSION` liest das Image `VERSION`; ein reiner `docker compose build web` funktioniert.
- Neuer Abschnitt „Entwicklungsmodus und Cache-Löschung“:
  - `?dev=1` aktiviert für die Tab-Session, `?dev=0` deaktiviert.
  - Wirkung: Service Worker abgemeldet, `vmkarte-`-Caches gelöscht, App-Version wird nicht geprüft.
  - Nutzer: Update-Hinweis bestätigen oder Website-Daten im Browser löschen.
  - Entwickler: DevTools → Application → Storage → Clear site data; optional Konsolen-Snippets zum Löschen der `vmkarte-`-Caches und Abmelden der Worker.
  - Hinweis: IndexedDB wird durch den Dev-Modus nicht gelöscht; das passiert weiterhin bei Logout und `401`.
- Neuer Abschnitt „Deployment und Rollback (Release 3.0)“:
  - Deployment nur `web`:

```bash
docker compose build web
docker compose up -d --force-recreate web
docker compose ps
curl -sS https://karte.jfr-service.de/app-version.json
```

  - Optional versionierter Build:

```bash
APP_VERSION=$(git describe --tags --always --dirty) \
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
docker compose build web
```

  - Verifikation von `Content-Type: application/json` und `Cache-Control: no-store`.
  - Rollback: vorheriges Image taggen (`docker tag …_web:latest …_web:rollback-<version>`) und zurückschalten, oder vorherigen Commit auschecken und neu bauen; `auth` und `cron` bleiben unberührt.
- Bestehende `vmkarte-shell-v5`-Erwähnungen in diesem Dokument auf `v6` aktualisieren.

**Doku-Inhalte für `DOKUMENTATION.md`:**
- Service-Worker-Abschnitt auf `vmkarte-shell-v6` aktualisieren.
- Satz ergänzen, dass `app-version.json` und `js/version.js` beim Docker-Build aus `VERSION` erzeugt werden.
- Update-Hinweis um die App-Version-Prüfung und `?dev=1` ergänzen.

**`local/ai/phases.md`:**
- Phase-9-Checkboxen abhaken.
- Stand-Absatz auf „Phase 0–9 implementiert …“ aktualisieren, sofern Deployment/Verifikation erfolgt sind; andernfalls Deployment als offen kennzeichnen.

**`local/ai/changelog.md`:**
- Neuen Phase-9-Eintrag oben ergänzen: Entscheidungen, Dateien, Tests, Commits, CACHE_NAME v6, offene Deployment-Schritte.

- [ ] **Step 1: Doku-Abschnitte ergänzen und v5 → v6 korrigieren.**
- [ ] **Step 2: `phases.md` und `changelog.md` aktualisieren.**
- [ ] **Step 3: Vollständige Verifikation ausführen**

```powershell
python -m unittest discover -s src/data_grabber/tests -p "test_*.py"
node --test tests/frontend
node tests/browser/phase8-cdp.mjs
node tests/browser/phase9-cdp.mjs
node --check docker/webserver/www_data/js/app.js
node --check docker/webserver/www_data/js/version.js
node --check docker/webserver/www_data/js/version-check.js
node --check docker/webserver/www_data/service-worker.js
```

Expected: alle Tests PASS, alle Syntaxchecks Exit 0.

- [ ] **Step 4: Commit**

```bash
git add docs/upgrade-3.0-auth.md DOKUMENTATION.md
git commit -m "docs: document versioning, cache and rollback"
```

`local/ai/phases.md` und `local/ai/changelog.md` bleiben untracked und werden nicht committet.

---

### Task 7: Merge, Push und Deployment

**Files:** keine Codeänderungen.

- [ ] **Step 1: Branch-Status prüfen**

```powershell
git status
git log --oneline release/3.0-pwa..HEAD
```

Expected: nur beabsichtigte Commits; `local/` bleibt untracked.

- [ ] **Step 2: Nach `release/3.0-pwa` mergen**

```powershell
git switch release/3.0-pwa
git merge --ff-only feature/phase9-version-dev-mode
```

- [ ] **Step 3: Push**

```powershell
git push origin release/3.0-pwa
```

- [ ] **Step 4: Nur das `web`-Image deployen**

```powershell
docker compose build web
docker compose up -d --force-recreate web
docker compose ps
```

- [ ] **Step 5: Deployment verifizieren**

```bash
curl -sS https://karte.jfr-service.de/app-version.json
curl -sSI https://karte.jfr-service.de/app-version.json | grep -iE 'content-type|cache-control'
```

Expected: `{"version":"3.0.0","buildDate":"…"}`, `application/json`, `Cache-Control: no-store`.

Danach im Browser prüfen:
- Karte lädt normal.
- `?dev=1` zeigt die Dev-Meldung und meldet den Service Worker ab.
- Ein Testbuild mit erhöhter Version zeigt nach dem Deployment den Update-Hinweis; ein Reload erfolgt erst nach Klick.
