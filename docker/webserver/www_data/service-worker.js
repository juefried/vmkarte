const CACHE_NAME = 'vmkarte-shell-v16';

const SHELL_URLS = [
	'/',
	'/karte.html',
	'/offline.html',
	'/manifest.webmanifest',
	'/geo-handler.html',
	'/icons/icon-192.png',
	'/icons/icon-512.png',
	'/icons/icon-maskable-512.png',
	'/icons/apple-touch-icon.png',
	'/screenshots/screenshot-wide.png',
	'/screenshots/screenshot-narrow.png',
	'/css/app.css',
	'/js/app.js',
	'/js/data.js',
	'/js/hashtags.js',
	'/js/storage.js',
	'/js/status-ui.js',
	'/js/map-state.js',
	'/js/search-fit.js',
	'/js/search-suggestions.js',
	'/js/location.js',
	'/js/version.js',
	'/js/version-check.js',
	'/js/geo-handler.js',
	'/leaflet/leaflet.css',
	'/leaflet/leaflet.js',
	'/markercluster/MarkerCluster.css',
	'/markercluster/MarkerCluster.Default.css',
	'/markercluster/leaflet.markercluster.js',
];

const NETWORK_ONLY_PATHS = new Set([
	'/login',
	'/logout',
	'/session-check',
	'/_internal/session-check',
	'/app-version.json',
]);

function isCacheableResponse(response) {
	return response.ok && !response.redirected;
}

async function precache() {
	const cache = await caches.open(CACHE_NAME);
	await Promise.all(SHELL_URLS.map(async url => {
		try {
			const response = await fetch(url, {
				cache: 'reload',
				credentials: 'same-origin',
			});
			if (isCacheableResponse(response))
				await cache.put(url, response);
		}
		catch (error) {
			// Offline, expired session or a missing optional asset must not
			// prevent the service worker from installing.
		}
	}));
}

self.addEventListener('install', event => {
	event.waitUntil(precache());
});

self.addEventListener('activate', event => {
	event.waitUntil((async () => {
		const keys = await caches.keys();
		await Promise.all(keys
			.filter(key => key.startsWith('vmkarte-') && key !== CACHE_NAME)
			.map(key => caches.delete(key)));
		await self.clients.claim();
	})());
});

self.addEventListener('message', event => {
	if (event.data && event.data.type === 'SKIP_WAITING')
		self.skipWaiting();
});

function isStaticAsset(pathname) {
	return pathname.startsWith('/css/')
		|| pathname.startsWith('/js/')
		|| pathname.startsWith('/leaflet/')
		|| pathname.startsWith('/markercluster/')
		|| pathname.startsWith('/icons/')
		|| pathname.startsWith('/screenshots/')
		|| pathname === '/favicon.ico';
}

async function networkFirstNavigation(request) {
	const cache = await caches.open(CACHE_NAME);
	try {
		const response = await fetch(request);
		if (isCacheableResponse(response))
			await cache.put(request, response.clone());
		return response;
	}
	catch (error) {
		return (await cache.match(request))
			|| (await cache.match('/karte.html'))
			|| (await cache.match('/'))
			|| (await cache.match('/offline.html'))
			|| Response.error();
	}
}

async function staleWhileRevalidate(request) {
	const cache = await caches.open(CACHE_NAME);
	const cached = await cache.match(request);
	const networkPromise = fetch(request)
		.then(async response => {
			if (response.ok)
				await cache.put(request, response.clone());
			return response;
		})
		.catch(() => null);

	if (cached)
		return cached;

	return (await networkPromise) || Response.error();
}

async function networkFirst(request) {
	const cache = await caches.open(CACHE_NAME);
	try {
		const response = await fetch(request);
		if (response.ok)
			await cache.put(request, response.clone());
		return response;
	}
	catch (error) {
		return (await cache.match(request)) || Response.error();
	}
}

self.addEventListener('fetch', event => {
	const request = event.request;
	if (request.method !== 'GET')
		return;

	const url = new URL(request.url);
	if (url.origin !== self.location.origin)
		return;
	if (url.pathname === '/service-worker.js')
		return;
	if (NETWORK_ONLY_PATHS.has(url.pathname) || url.pathname.startsWith('/shared/'))
		return;

	if (request.mode === 'navigate') {
		event.respondWith(networkFirstNavigation(request));
		return;
	}

	if (isStaticAsset(url.pathname)) {
		event.respondWith(staleWhileRevalidate(request));
		return;
	}

	event.respondWith(networkFirst(request));
});
