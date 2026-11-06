// Phase 9 end-to-end regression test (manual).
// Requires Node 22+ and a local Chrome/Chromium.
// Run: node tests/browser/phase9-cdp.mjs
// Optional: CHROME_PATH=/path/to/chrome node tests/browser/phase9-cdp.mjs

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../../docker/webserver/www_data', import.meta.url));
let TEMP = '';
const CHROME_CANDIDATES = [
	process.env.CHROME_PATH,
	'C:/Program Files/Google/Chrome/Application/chrome.exe',
	'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
	process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, 'Google/Chrome/Application/chrome.exe'),
	'/usr/bin/google-chrome',
	'/usr/bin/chromium',
	'/usr/bin/chromium-browser',
	'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean);
const CHROME = CHROME_CANDIDATES.find(candidate => existsSync(candidate));
if (!CHROME)
	throw new Error('Chrome/Chromium not found. Set CHROME_PATH.');
let ORIGIN = '';

const members = [
	{ id: '1', name: 'Alpha', lat: 50.0, lon: 11.0, vm: 'Flevo', lr: '', tr: '', other: '#berlin #übernachtung', profile_updated_at: '2026-11-01' },
	{ id: '2', name: 'Beta', lat: 50.1, lon: 11.1, vm: '', lr: 'Liegerad', tr: '', other: '', profile_updated_at: '2026-11-01' },
	{ id: '3', name: 'Gamma', lat: 50.2, lon: 11.2, vm: 'Quest', lr: '', tr: '', other: '#berlin', profile_updated_at: '2026-11-01' },
];
const dataStatus = {
	runStartedAt: '2026-11-06T03:33:00+01:00',
	generatedAt: '2026-11-06T03:41:12+01:00',
	memberCount: members.length,
};

let membersUnauthorized = false;
let appVersion = { version: 'dev', buildDate: '2026-11-06T10:00:00Z' };
let appVersionStatus = 200;
let chrome = null;
let server = null;

function contentType(path) {
	const types = {
		'.html': 'text/html; charset=utf-8',
		'.js': 'application/javascript; charset=utf-8',
		'.css': 'text/css; charset=utf-8',
		'.json': 'application/json',
		'.webmanifest': 'application/manifest+json',
		'.png': 'image/png',
		'.svg': 'image/svg+xml',
	};
	return types[extname(path)] || 'application/octet-stream';
}

function sendJson(res, value) {
	res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
	res.end(JSON.stringify(value));
}

async function startServer() {
	server = createServer(async (req, res) => {
		const url = new URL(req.url, ORIGIN || 'http://127.0.0.1');

		if (url.pathname === '/__test/401') {
			membersUnauthorized = url.searchParams.get('off') !== '1';
			res.writeHead(200, { 'content-type': 'text/plain' });
			res.end('ok');
			return;
		}

		if (url.pathname === '/app-version.json') {
			if (appVersionStatus !== 200) {
				res.writeHead(appVersionStatus, { 'content-type': 'application/json', 'cache-control': 'no-store' });
				res.end('{"error":"test"}');
				return;
			}
			sendJson(res, appVersion);
			return;
		}

		if (url.pathname === '/shared/data-status.json') {
			sendJson(res, dataStatus);
			return;
		}

		if (url.pathname === '/shared/vmforum_members.json') {
			if (membersUnauthorized) {
				res.writeHead(401, { 'content-type': 'application/json' });
				res.end('{"error":"unauthorized"}');
				return;
			}
			sendJson(res, members);
			return;
		}

		if (url.pathname === '/logout' && req.method === 'POST') {
			res.writeHead(200, { 'content-type': 'text/plain' });
			res.end('ok');
			return;
		}

		if (url.pathname === '/login') {
			res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
			res.end('<!doctype html><meta charset="utf-8"><title>Login</title>');
			return;
		}

		let pathname = url.pathname === '/' ? '/karte.html' : url.pathname;
		const filePath = normalize(join(ROOT, pathname));
		if (!filePath.startsWith(normalize(ROOT))) {
			res.writeHead(403);
			res.end();
			return;
		}

		try {
			const body = await readFile(filePath);
			res.writeHead(200, { 'content-type': contentType(filePath), 'cache-control': 'no-store' });
			res.end(body);
		}
		catch {
			res.writeHead(404, { 'content-type': 'text/plain' });
			res.end('not found');
		}
	});
	await new Promise((resolve, reject) => {
		server.once('error', reject);
		server.listen(0, '127.0.0.1', resolve);
	});
	ORIGIN = `http://127.0.0.1:${server.address().port}`;
}

async function waitForJson(url, timeout = 15000) {
	const end = Date.now() + timeout;
	let lastError = null;
	while (Date.now() < end) {
		try {
			const response = await fetch(url);
			if (response.ok)
				return await response.json();
		}
		catch (error) {
			lastError = error;
		}
		await new Promise(resolve => setTimeout(resolve, 100));
	}
	throw lastError || new Error(`Timeout waiting for ${url}`);
}

function connect(wsUrl) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(wsUrl);
		const pending = new Map();
		const listeners = new Map();
		let nextId = 0;

		const client = {
			ws,
			send(method, params = {}) {
				const id = ++nextId;
				return new Promise((res, rej) => {
					pending.set(id, { res, rej });
					ws.send(JSON.stringify({ id, method, params }));
				});
			},
			on(method, handler) {
				if (!listeners.has(method))
					listeners.set(method, []);
				listeners.get(method).push(handler);
			},
		};

		ws.addEventListener('open', () => resolve(client));
		ws.addEventListener('error', event => reject(event.error || new Error('WebSocket error')));
		ws.addEventListener('message', event => {
			const message = JSON.parse(event.data);
			if (message.id) {
				const entry = pending.get(message.id);
				if (!entry)
					return;
				pending.delete(message.id);
				if (message.error)
					entry.rej(new Error(JSON.stringify(message.error)));
				else
					entry.res(message.result);
				return;
			}
			for (const handler of listeners.get(message.method) || [])
				handler(message.params);
		});
	});
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function waitForDebugPort(timeout = 15000) {
	const file = join(TEMP, 'profile', 'DevToolsActivePort');
	const end = Date.now() + timeout;
	while (Date.now() < end) {
		try {
			const content = await readFile(file, 'utf8');
			const port = Number(content.trim().split(/\r?\n/)[0]);
			if (Number.isInteger(port) && port > 0)
				return port;
		}
		catch {
			// Chrome has not written the file yet.
		}
		await delay(100);
	}
	throw new Error('Chrome DevToolsActivePort not found');
}

function checks() {
	let count = 0;
	return {
		pass(message) {
			count += 1;
			console.log(`PASS ${count}: ${message}`);
		},
		get count() {
			return count;
		},
	};
}

async function main() {
	const check = checks();
	TEMP = await mkdtemp(join(tmpdir(), 'vmkarte-phase9-'));
	await startServer();
	console.log(`Local server: ${ORIGIN}`);

	chrome = spawn(CHROME, [
		'--headless=new',
		'--disable-gpu',
		'--hide-scrollbars',
		'--no-first-run',
		'--no-default-browser-check',
		'--disable-extensions',
		'--disable-sync',
		'--disable-default-apps',
		'--disable-background-networking',
		'--disable-component-update',
		'--user-data-dir=' + join(TEMP, 'profile'),
		'--remote-debugging-port=0',
		'--window-size=1280,900',
		'about:blank',
	], { stdio: 'ignore' });

	const debugPort = await waitForDebugPort();
	const version = await waitForJson(`http://127.0.0.1:${debugPort}/json/version`);
	let targets = await waitForJson(`http://127.0.0.1:${debugPort}/json/list`);
	if (!targets.some(target => target.type === 'page')) {
		await fetch(`http://127.0.0.1:${debugPort}/json/new?about:blank`, { method: 'PUT' });
		targets = await waitForJson(`http://127.0.0.1:${debugPort}/json/list`);
	}
	const pageTarget = targets.find(target => target.type === 'page');
	assert.ok(pageTarget, 'Chrome page target');

	const browser = await connect(version.webSocketDebuggerUrl);
	const page = await connect(pageTarget.webSocketDebuggerUrl);

	await page.send('Page.enable');
	await page.send('Runtime.enable');
	await page.send('Network.enable');

	async function evaluate(expression) {
		const result = await page.send('Runtime.evaluate', {
			expression,
			awaitPromise: true,
			returnByValue: true,
			userGesture: true,
		});
		if (result.exceptionDetails) {
			const description = result.exceptionDetails.exception?.description
				|| result.exceptionDetails.text;
			throw new Error(description);
		}
		return result.result.value;
	}

	async function waitFor(expression, label, timeout = 15000) {
		const end = Date.now() + timeout;
		let lastError = null;
		while (Date.now() < end) {
			try {
				if (await evaluate(expression))
					return;
			}
			catch (error) {
				lastError = error;
			}
			await delay(100);
		}
		throw new Error(`Timeout waiting for ${label}${lastError ? `: ${lastError.message}` : ''}`);
	}

	async function navigate(path) {
		await page.send('Page.navigate', { url: ORIGIN + path });
		await waitFor(`document.readyState === 'complete'`, `load ${path}`, 20000);
	}

	async function waitForMap() {
		await waitFor(`document.querySelector('.leaflet-container') !== null`, 'map container');
		await waitFor(`document.querySelectorAll('img.leaflet-tile').length > 0`, 'map tiles');
		await waitFor(`document.querySelectorAll('.leaflet-marker-icon').length > 0`, 'member markers');
	}

	async function openMarkerPopup() {
		await waitFor(`document.querySelectorAll('.leaflet-marker-icon').length > 0`, 'marker icons');
		for (let attempt = 0; attempt < 8; attempt += 1) {
			if (await evaluate(`document.querySelector('.leaflet-popup-content') !== null`))
				return;
			await evaluate(`document.querySelector('.leaflet-marker-icon').click()`);
			await delay(400);
		}
		await waitFor(`document.querySelector('.leaflet-popup-content') !== null`, 'marker popup');
	}

	async function cacheContains(url) {
		return evaluate(`(async () => {
			for (const key of await caches.keys()) {
				const cache = await caches.open(key);
				if (await cache.match(${JSON.stringify(url)}))
					return true;
			}
			return false;
		})()`);
	}

	// 1. Start with matching version: no update message.
	appVersion = { version: 'dev', buildDate: '2026-11-06T10:00:00Z' };
	appVersionStatus = 200;
	await navigate('/karte.html');
	await waitForMap();
	await delay(300);
	assert.equal(await evaluate(`document.getElementById('data_message').textContent.includes('neue Version')`), false);
	assert.equal(await evaluate(`document.getElementById('search_suggestions').hidden`), true);
	await evaluate(`(() => {
		const input = document.getElementById('form_search');
		input.focus();
		input.dispatchEvent(new FocusEvent('focus'));
	})()`);
	await waitFor(`document.getElementById('search_suggestions').hidden === false`, 'empty search suggestions');
	assert.deepEqual(
		await evaluate(`Array.from(document.querySelectorAll('#search_suggestions [role="option"]')).map(option => option.textContent)`),
		['#berlin', '#übernachtung'],
	);
	assert.equal(await evaluate(`getComputedStyle(document.getElementById('search_suggestions')).overflowY`), 'auto');
	assert.notEqual(await evaluate(`getComputedStyle(document.getElementById('search_suggestions')).maxHeight`), 'none');
	await evaluate(`(() => {
		const input = document.getElementById('form_search');
		input.value = 'Al';
		input.dispatchEvent(new Event('input', { bubbles: true }));
	})()`);
	assert.deepEqual(
		await evaluate(`Array.from(document.querySelectorAll('#search_suggestions [role="option"]')).map(option => option.textContent)`),
		['Alpha'],
	);
	await evaluate(`(() => {
		const input = document.getElementById('form_search');
		input.value = 'Fle';
		input.dispatchEvent(new Event('input', { bubbles: true }));
	})()`);
	assert.deepEqual(
		await evaluate(`Array.from(document.querySelectorAll('#search_suggestions [role="option"]')).map(option => option.textContent)`),
		['Flevo'],
	);

	await page.send('Page.bringToFront');
	await delay(100);
	const listRect = await evaluate(`(() => {
		const list = document.getElementById('search_suggestions');
		list.dataset.originalHtml = list.innerHTML;
		for (let index = 0; index < 20; index += 1) {
			const option = document.createElement('li');
			option.setAttribute('role', 'option');
			option.textContent = 'Scrolltest ' + index;
			list.appendChild(option);
		}
		list.style.maxHeight = '60px';
		const rect = list.getBoundingClientRect();
		return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
	})()`);
	const listInteraction = await evaluate(`(() => {
		const list = document.getElementById('search_suggestions');
		const mapContainer = document.querySelector('.leaflet-container');
		let reached = 0;
		const onEvent = () => { reached += 1; };
		for (const type of ['wheel', 'mousedown', 'touchstart'])
			mapContainer.addEventListener(type, onEvent);
		list.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 120 }));
		list.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0, buttons: 1 }));
		list.dispatchEvent(new Event('touchstart', { bubbles: true, cancelable: true }));
		for (const type of ['wheel', 'mousedown', 'touchstart'])
			mapContainer.removeEventListener(type, onEvent);
		return { reached, touchAction: getComputedStyle(list).touchAction };
	})()`);
	assert.equal(listInteraction.reached, 0);
	assert.equal(listInteraction.touchAction, 'pan-y');
	await page.send('Input.dispatchMouseEvent', {
		type: 'mouseWheel',
		x: listRect.x,
		y: listRect.y,
		button: 'none',
		clickCount: 0,
		deltaX: 0,
		deltaY: 120,
	});
	await delay(150);
	assert.ok(await evaluate(`document.getElementById('search_suggestions').scrollTop > 0`));
	await evaluate(`(() => {
		const list = document.getElementById('search_suggestions');
		list.innerHTML = list.dataset.originalHtml;
		delete list.dataset.originalHtml;
		list.style.maxHeight = '';
	})()`);
	check.pass('Suchvorschläge scrollen unabhängig von der Karte');

	await evaluate(`document.querySelector('#search_suggestions [role="option"]').click()`);
	assert.equal(await evaluate(`document.getElementById('form_search').value`), 'Flevo');
	assert.equal(await evaluate(`document.getElementById('search_suggestions').hidden`), true);
	await evaluate(`(() => {
		const input = document.getElementById('form_search');
		input.value = '';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
		input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
	})()`);
	assert.equal(await evaluate(`document.getElementById('form_search').value`), '#berlin');
	assert.equal(await evaluate(`document.getElementById('form_select').selectedIndex`), 7);
	assert.equal(await evaluate(`document.getElementById('search_suggestions').hidden`), true);
	check.pass('Leeres Suchfeld zeigt nur Unicode-Hashtags; Eingaben filtern Namen und Fahrzeuge; Auswahl per Klick und Tastatur funktioniert');

	// 1b. The manual refresh button also checks the app version.
	appVersion = { version: '9.9.9', buildDate: '2026-11-07T10:00:00Z' };
	await evaluate(`document.getElementById('refresh_button').click()`);
	await waitFor(`document.getElementById('data_message').textContent.includes('Eine neue Version ist verfügbar.')`, 'update message after manual refresh');
	check.pass('Der manuelle Reload prüft zusätzlich die App-Version');

	// 2. Service worker installs and does not cache app-version.json.
	await waitFor(`navigator.serviceWorker.getRegistration().then(registration => Boolean(registration))`, 'service worker registration');
	await waitFor(`caches.keys().then(keys => keys.some(key => key.startsWith('vmkarte-')))`, 'app shell cache');
	assert.equal(await cacheContains('/app-version.json'), false);
	const serviceWorkerSource = await (await fetch(ORIGIN + '/service-worker.js')).text();
	assert.ok(serviceWorkerSource.includes("const CACHE_NAME = 'vmkarte-shell-v13';"));
	check.pass('Service Worker installiert, Cache ist v13 und app-version.json bleibt network-only');

	// 3. ?dev=1 disables the service worker, removes caches and skips the version check.
	appVersion = { version: '9.9.9', buildDate: '2026-11-07T10:00:00Z' };
	await navigate('/karte.html?dev=1');
	await waitForMap();
	await waitFor(`document.getElementById('data_message').textContent.includes('Entwicklungsmodus aktiv')`, 'dev mode message');
	assert.equal(await evaluate(`document.getElementById('data_message').textContent.includes('Eine neue Version ist verfügbar.')`), false);
	await waitFor(`navigator.serviceWorker.getRegistrations().then(registrations => registrations.length === 0)`, 'service workers unregistered');
	await waitFor(`caches.keys().then(keys => keys.filter(key => key.startsWith('vmkarte-')).length === 0)`, 'vmkarte caches deleted');
	check.pass('?dev=1 meldet Service Worker ab, löscht Caches und überspringt die Versionsprüfung');

	// 3b. The dev mode persists across a navigation without the query parameter.
	await navigate('/karte.html');
	await waitForMap();
	await waitFor(`document.getElementById('data_message').textContent.includes('Entwicklungsmodus aktiv')`, 'persisted dev mode message');
	assert.equal(await evaluate(`navigator.serviceWorker.getRegistrations().then(registrations => registrations.length)`), 0);
	check.pass('Entwicklungsmodus bleibt in der Tab-Session ohne Parameter aktiv');

	// 4. ?dev=0 disables dev mode and registers the worker again.
	appVersion = { version: 'dev', buildDate: '2026-11-06T10:00:00Z' };
	await navigate('/karte.html?dev=0');
	await waitForMap();
	await delay(300);
	assert.equal(await evaluate(`document.getElementById('data_message').textContent.includes('Entwicklungsmodus')`), false);
	await waitFor(`navigator.serviceWorker.getRegistration().then(registration => Boolean(registration))`, 'service worker registration after dev=0');
	await waitFor(`caches.keys().then(keys => keys.some(key => key.startsWith('vmkarte-')))`, 'app shell cache after dev=0');
	check.pass('?dev=0 deaktiviert den Entwicklungsmodus und registriert den Worker erneut');

	// 5. A different app version shows a hint that reloads only after confirmation.
	appVersion = { version: '9.9.9', buildDate: '2026-11-07T10:00:00Z' };
	await navigate('/karte.html');
	await waitForMap();
	await waitFor(`document.getElementById('data_message').textContent.includes('Eine neue Version ist verfügbar.')`, 'update message');
	assert.equal(await evaluate(`Array.from(document.querySelectorAll('#data_message button')).some(button => button.textContent === 'Neu laden')`), true);
	await evaluate(`window.__phase9Sentinel = true`);
	await delay(1500);
	assert.equal(await evaluate(`window.__phase9Sentinel`), true);
	assert.equal(await evaluate(`location.pathname`), '/karte.html');
	check.pass('Neue App-Version zeigt Hinweis und lädt nicht automatisch neu');

	await evaluate(`(() => {
		const button = Array.from(document.querySelectorAll('#data_message button'))
			.find(candidate => candidate.textContent === 'Neu laden');
		button.click();
		return true;
	})()`);
	await waitFor(`typeof window.__phase9Sentinel === 'undefined'`, 'confirmed reload', 20000);
	await waitForMap();
	await waitFor(`document.getElementById('data_message').textContent.includes('Eine neue Version ist verfügbar.')`, 'update message after reload');
	check.pass('Neu laden wird erst nach Bestätigung ausgeführt');

	// 6. A failed version request stays silent.
	appVersionStatus = 500;
	await navigate('/karte.html');
	await waitForMap();
	await delay(500);
	assert.equal(await evaluate(`document.getElementById('data_message').textContent.includes('neue Version')`), false);
	assert.equal(await evaluate(`document.getElementById('data_message').classList.contains('data-message-error')`), false);
	assert.equal(await evaluate(`document.querySelectorAll('.leaflet-marker-icon').length > 0`), true);
	check.pass('Fehler bei app-version.json bleibt ohne Meldung und blockiert die Karte nicht');

	// 7. Forum profile links open in a new tab; hashtag and geo links stay in place.
	appVersionStatus = 200;
	await navigate('/karte.html?other=%23berlin');
	await waitForMap();
	await openMarkerPopup();
	const profileSelector = '.leaflet-popup-content a[title="Mitglieder-Profil im Forum"]';
	assert.equal(await evaluate(`Boolean(document.querySelector(${JSON.stringify(profileSelector)}))`), true);
	assert.equal(await evaluate(`document.querySelector(${JSON.stringify(profileSelector)}).target`), '_blank');
	assert.equal(await evaluate(`document.querySelector(${JSON.stringify(profileSelector)}).relList.contains('noopener')`), true);
	assert.equal(await evaluate(`document.querySelector('.leaflet-popup-content a[href^="karte.html?other="]').getAttribute('target')`), null);
	assert.equal(await evaluate(`document.querySelector('.leaflet-popup-content a[href^="geo:"]').getAttribute('target')`), null);
	check.pass('Forenprofil-Links öffnen in einem neuen Tab; Hashtag- und geo-Links bleiben im selben Tab');

	console.log(`\n${check.count} browser checks passed.`);
}

try {
	await main();
}
catch (error) {
	console.error('\nBROWSER TEST FAILED');
	console.error(error);
	process.exitCode = 1;
}
finally {
	if (chrome)
		chrome.kill();
	if (server)
		server.close();
	if (TEMP) {
		await new Promise(resolve => setTimeout(resolve, 300));
		await rm(TEMP, { recursive: true, force: true }).catch(() => {});
	}
}
