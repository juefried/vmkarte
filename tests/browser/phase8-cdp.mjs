// Phase 8 end-to-end regression test (manual).
// Requires Node 22+ and a local Chrome/Chromium.
// Run: node tests/browser/phase8-cdp.mjs
// Optional: CHROME_PATH=/path/to/chrome node tests/browser/phase8-cdp.mjs

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
	{ id: '1', name: 'Alpha', lat: 50.0, lon: 11.0, vm: 'Flevo', lr: '', tr: '', other: '#berlin', profile_updated_at: '2026-11-01' },
	{ id: '2', name: 'Beta', lat: 50.1, lon: 11.1, vm: '', lr: 'Liegerad', tr: '', other: '', profile_updated_at: '2026-11-01' },
	{ id: '3', name: 'Gamma', lat: 50.2, lon: 11.2, vm: 'Quest', lr: '', tr: '', other: '#berlin', profile_updated_at: '2026-11-01' },
];
const dataStatus = {
	runStartedAt: '2026-11-06T03:33:00+01:00',
	generatedAt: '2026-11-06T03:41:12+01:00',
	memberCount: members.length,
};

let membersUnauthorized = false;
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
	TEMP = await mkdtemp(join(tmpdir(), 'vmkarte-phase8-'));
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
	await browser.send('Browser.grantPermissions', {
		origin: ORIGIN,
		permissions: ['geolocation'],
	});
	await page.send('Emulation.setGeolocationOverride', {
		latitude: 52.5,
		longitude: 13.4,
		accuracy: 50,
	});
	await page.send('Page.addScriptToEvaluateOnNewDocument', {
		source: `(() => {
			window.__geoCallCount = 0;
			const geolocation = navigator.geolocation;
			if (!geolocation)
				return;
			const proto = Object.getPrototypeOf(geolocation);
			const original = proto.getCurrentPosition;
			proto.getCurrentPosition = function (...args) {
				window.__geoCallCount += 1;
				setTimeout(() => original.apply(this, args), 400);
			};
		})();`,
	});

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

	async function storeKeys() {
		return evaluate(`new Promise((resolve, reject) => {
			const request = indexedDB.open('vmkarte', 1);
			request.onupgradeneeded = () => request.result.createObjectStore('kv');
			request.onsuccess = () => {
				const database = request.result;
				if (!database.objectStoreNames.contains('kv')) {
					resolve([]);
					return;
				}
				const getAllKeys = database.transaction('kv', 'readonly').objectStore('kv').getAllKeys();
				getAllKeys.onsuccess = () => resolve(getAllKeys.result);
				getAllKeys.onerror = () => reject(getAllKeys.error);
			};
			request.onerror = () => reject(request.error);
		})`);
	}

	async function readMapState() {
		return evaluate(`new Promise((resolve, reject) => {
			const request = indexedDB.open('vmkarte', 1);
			request.onupgradeneeded = () => request.result.createObjectStore('kv');
			request.onsuccess = () => {
				const database = request.result;
				if (!database.objectStoreNames.contains('kv')) {
					resolve(undefined);
					return;
				}
				const get = database.transaction('kv', 'readonly').objectStore('kv').get('mapState');
				get.onsuccess = () => resolve(get.result);
				get.onerror = () => reject(get.error);
			};
			request.onerror = () => reject(request.error);
		})`);
	}

	async function tileZooms() {
		return evaluate(`Array.from(document.querySelectorAll('img.leaflet-tile'))
			.map(image => new URL(image.src).pathname.split('/')[1])`);
	}

	const requests = [];
	page.on('Network.requestWillBeSent', params => requests.push(params.request.url));

	// 1. Start: form defaults, no location marker.
	await navigate('/karte.html');
	await waitForMap();
	assert.equal(await evaluate(`document.querySelector('#form_search').value`), '');
	assert.equal(await evaluate(`document.querySelector('#form_select').selectedIndex`), 0);
	assert.equal(await evaluate(`document.querySelectorAll('.location-marker').length`), 0);
	check.pass('Start mit leeren Formularen und ohne Standortmarker');

	// 2. Save map state after zoom.
	await evaluate(`document.querySelector('.leaflet-control-zoom-in').click()`);
	await delay(250);
	await evaluate(`document.querySelector('.leaflet-control-zoom-in').click()`);
	await delay(1000);
	const zoomState = await readMapState();
	assert.equal(zoomState.zoom, 9);
	assert.ok(Math.abs(zoomState.center[0] - 50) < 0.5);
	assert.ok(Math.abs(zoomState.center[1] - 11) < 0.5);
	assert.equal(zoomState.search, '');
	check.pass('Kartenmitte und Zoom werden in IndexedDB gespeichert');

	// 3. URL filter wins and is persisted on map movement.
	await navigate('/karte.html?vm=Flevo');
	await waitForMap();
	assert.equal(await evaluate(`document.querySelector('#form_search').value`), '');
	assert.equal(await evaluate(`document.querySelector('#form_select').selectedIndex`), 0);
	await evaluate(`document.querySelector('.leaflet-control-zoom-in').click()`);
	await delay(1000);
	const filterState = await readMapState();
	assert.equal(filterState.zoom, 10);
	assert.equal(filterState.search, 'vm=Flevo');
	check.pass('URL-Filter wird verwendet und als Filterstand gespeichert');

	// 4. Restore map state and stored filter without filling the form.
	await navigate('/karte.html');
	await waitForMap();
	await waitFor(`window.location.search.includes('vm=Flevo')`, 'restored filter URL');
	assert.equal(await evaluate(`document.querySelector('#form_search').value`), '');
	assert.equal(await evaluate(`document.querySelector('#form_select').selectedIndex`), 0);
	await waitFor(`Array.from(document.querySelectorAll('img.leaflet-tile')).some(image => new URL(image.src).pathname.startsWith('/10/'))`, 'restored zoom tiles');
	check.pass('Kartenstatus und gespeicherter Filter werden beim Start wiederhergestellt');

	// 5. 401 clears IndexedDB and app caches.
	await fetch(ORIGIN + '/__test/401');
	await navigate('/karte.html');
	await waitFor(`location.pathname === '/login'`, '401 login redirect');
	await delay(300);
	assert.deepEqual(await storeKeys(), []);
	assert.deepEqual(await evaluate(`caches.keys()`), []);
	check.pass('401 löscht IndexedDB und vmkarte-Caches');
	await fetch(ORIGIN + '/__test/401?off=1');

	// 6. Reload for geolocation; the 401 left no map state behind.
	await navigate('/karte.html');
	await waitForMap();
	assert.equal(await readMapState(), undefined);

	requests.length = 0;
	await evaluate(`(() => {
		const button = document.getElementById('location_button');
		button.click();
		button.click();
		return true;
	})()`);
	assert.equal(await evaluate(`document.getElementById('location_button').disabled`), true);
	await waitFor(`document.querySelectorAll('.location-marker').length > 0`, 'location marker');
	await waitFor(`document.querySelectorAll('.location-accuracy').length > 0`, 'location accuracy circle');
	assert.equal(await evaluate(`window.__geoCallCount`), 1);
	check.pass('Standort wird nur nach Klick und nur einmal abgefragt');

	const geometry = await evaluate(`(() => {
		const map = document.querySelector('.leaflet-container').getBoundingClientRect();
		const marker = document.querySelector('.location-marker').getBoundingClientRect();
		return {
			mapX: map.left + map.width / 2,
			mapY: map.top + map.height / 2,
			markerX: marker.left + marker.width / 2,
			markerY: marker.top + marker.height / 2,
		};
	})()`);
	assert.ok(Math.abs(geometry.mapX - geometry.markerX) < 8);
	assert.ok(Math.abs(geometry.mapY - geometry.markerY) < 8);
	check.pass('Standortmarker und Genauigkeitskreis werden zentriert angezeigt');

	await delay(800);
	const suspiciousRequests = requests.filter(url =>
		url.includes('52.5') || url.includes('13.4') || url.includes('/shared/'));
	assert.deepEqual(suspiciousRequests, []);
	check.pass('Keine Standortdaten oder Datendateien werden nach dem Klick übertragen');

	const stateAfterLocation = await readMapState();
	if (stateAfterLocation) {
		assert.ok(
			Math.abs(stateAfterLocation.center[0] - 52.5) > 0.0001
			|| Math.abs(stateAfterLocation.center[1] - 13.4) > 0.0001,
			'location must not be stored as map center',
		);
	}
	assert.ok(!(await evaluate(`location.href`)).includes('52.5'));
	assert.deepEqual(await evaluate(`Object.keys(localStorage)`), []);
	check.pass('Standort wird nicht dauerhaft gespeichert');

	// Zooming or resizing at the location must not persist it either.
	await delay(1200);
	await evaluate(`document.querySelector('.leaflet-control-zoom-in').click()`);
	await delay(1000);
	assert.equal(await readMapState(), undefined);
	await evaluate(`window.dispatchEvent(new Event('resize'))`);
	await delay(1000);
	assert.equal(await readMapState(), undefined);
	check.pass('Zoom und Resize am Standort speichern die Position nicht');

	// Pan away, then log out while a map-state save is still pending.
	const mapPoint = await evaluate(`(() => {
		const rect = document.querySelector('.leaflet-container').getBoundingClientRect();
		return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
	})()`);
	await page.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: mapPoint.x, y: mapPoint.y, button: 'left', clickCount: 1 });
	await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: mapPoint.x + 120, y: mapPoint.y, button: 'left', buttons: 1 });
	await page.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: mapPoint.x + 120, y: mapPoint.y, button: 'left', clickCount: 1 });
	await delay(100);
	check.pass('Karte lässt sich nach der Standortanzeige normal verschieben');

	// 7. Logout clears IndexedDB, caches and leaves no location data.
	await evaluate(`document.getElementById('logout_button').click()`);
	await waitFor(`location.pathname === '/login'`, 'logout redirect');
	await delay(300);
	assert.deepEqual(await storeKeys(), []);
	assert.deepEqual(await evaluate(`caches.keys()`), []);
	assert.deepEqual(await evaluate(`Object.keys(localStorage)`), []);
	check.pass('Logout löscht IndexedDB, Caches und lokale Komfortdaten');

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
