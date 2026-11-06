# Phase 7 – Service Worker und Offline-App-Shell

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Karte lädt die App-Shell aus dem Service-Worker-Cache, sodass ein Reload offline funktioniert; Daten bleiben network-only und kommen offline aus IndexedDB.

**Architecture:** Ein klassischer Service Worker unter `/service-worker.js` precacht App-Shell und statische Assets, bedient Navigationen network-first mit Cache-Fallback und statische Assets stale-while-revalidate. `/shared/`, `/login`, `/logout` und Session-Checks bleiben network-only. Die Seite registriert den Worker, zeigt einen Update-Hinweis und löscht bei Logout/`401` auch die Cache-Storage-Einträge.

**Tech Stack:** Service Worker API, Cache Storage, IndexedDB (bestehend), natives JavaScript, nginx.

**Spec:** `local/ai/requirements.md`, `local/ai/phases.md` (Phase 7), `docs/superpowers/specs/2026-11-06-phase5-frontend-data-loader-design.md`

## Global Constraints

- Keine Änderungen an API-Abruf, Geocoding oder `data-status.json`.
- `/shared/` und `data-status.json` bleiben network-only.
- `/login`, `/logout`, `/session-check` werden nicht gecacht.
- Keine Zugangsdaten oder Cookies im Service Worker.
- `local/ai/` bleibt untracked.
- Bestehende Phase-5-Funktionen bleiben erhalten.
- Update-Reload nur nach Bestätigung.

## Task 1: Service Worker und Offline-Seite

**Files:**
- Create: `docker/webserver/www_data/service-worker.js`
- Create: `docker/webserver/www_data/offline.html`

**Interfaces:**
- `CACHE_NAME = 'vmkarte-shell-v1'`
- Precacht `/`, `/karte.html`, `/offline.html`, CSS/JS-Module, Leaflet, MarkerCluster und `geo-handler.html`.
- Navigation: network-first, Cache-Fallback auf Request, `/karte.html`, `/`, `/offline.html`.
- Statische Assets: stale-while-revalidate.
- `/shared/`, `/login`, `/logout`, `/session-check`, `/_internal/session-check`, `/service-worker.js` und Nicht-GET: network-only.
- `message` mit `{type:'SKIP_WAITING'}` ruft `self.skipWaiting()` auf.
- `activate` löscht alte `vmkarte-`-Caches und ruft `clients.claim()`.

- [ ] **Step 1: `service-worker.js` anlegen** mit den oben genannten Funktionen. Beim Precachen pro URL `fetch(url, {cache:'reload', credentials:'same-origin'})`; nur `response.ok && !response.redirected` cachen, damit eine Login-Weiterleitung nicht als App-Shell landet.
- [ ] **Step 2: `offline.html` anlegen** mit verständlicher Meldung und Link auf `/`. Keine Inline-Skripte.
- [ ] **Step 3: `node --check docker/webserver/www_data/service-worker.js`** ausführen.

## Task 2: Registrierung, Update-Hinweis und Cache-Löschung

**Files:**
- Modify: `docker/webserver/www_data/js/status-ui.js`
- Modify: `docker/webserver/www_data/js/app.js`

**Interfaces:**
- `setMessage({ type, text, onRetry, actionLabel = 'Erneut versuchen', autoHideMs = null })`
- `register_service_worker()` registriert `/service-worker.js`, zeigt bei `installed` + vorhandenem Controller den Update-Hinweis mit Aktion „Neu laden“ und sendet bei Bestätigung `SKIP_WAITING`, danach einmalig `location.reload()`.
- `clearAppCaches()` löscht alle Cache-Storage-Keys mit Präfix `vmkarte-`.
- `logout()` und `handleUnauthorized()` rufen `clearCache()` und `clearAppCaches()` auf.

- [ ] **Step 1: `status-ui.js` erweitern** um `actionLabel` und `autoHideMs`.
- [ ] **Step 2: `app.js` erweitern** um `clearAppCaches`, `register_service_worker`, Aufruf nach `syncFromServer()`, und Cache-Löschung bei Logout/401.
- [ ] **Step 3: Syntax prüfen** mit `node --check` für `app.js` und `status-ui.js`.

## Task 3: Verifikation und Dokumentation

**Files:**
- Modify: `docs/upgrade-3.0-auth.md`
- Modify: `DOKUMENTATION.md`
- Modify: `local/ai/phases.md`
- Modify: `local/ai/changelog.md`

- [ ] **Step 1: Node- und Python-Tests ausführen.**
- [ ] **Step 2: Headless-Chrome/CDP mit lokalem Testserver:**
  - Online laden, warten bis `caches.keys()` `vmkarte-shell-v1` enthält.
  - Prüfen, dass `/shared/vmforum_members.json` nicht im Cache liegt.
  - Offline schalten, `/karte.html` neu laden: App-Shell lädt, Marker aus IndexedDB, Status `lokal (Aktualisierung fehlgeschlagen)`, Offline-Badge sichtbar.
  - Logout: Cache-Storage enthält danach keine `vmkarte-`-Keys.
- [ ] **Step 3: Dokumentation aktualisieren** (Service-Worker-Verhalten, Cache-Version bumpen, Offline-Reload).
- [ ] **Step 4: Commit, Merge nach `release/3.0-pwa`, Push.**
