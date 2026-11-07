import { readCache, writeCache, clearCache, readMapState, writeMapState } from './storage.js';
import { createStatusUi } from './status-ui.js';
import { validateMembers, parseDataStatus, deriveStatusFromLastModified } from './data.js';
import { resolveInitialMapState, filterSearchString, FILTER_PARAMS, shouldPersistMapState } from './map-state.js';
import { HASHTAG_REGEX, HASHTAG_NAME_REGEX } from './hashtags.js';
import { collectSearchSuggestions, filterSearchSuggestions } from './search-suggestions.js';
import {
	SEARCH_FIT_PADDING,
	clampSearchZoom,
	findClosestFittingCenter,
	findDensestCenter,
	isPortraitSize,
	shouldAdjustSearchView,
} from './search-fit.js';
import { describeGeolocationError, GEOLOCATION_OPTIONS } from './location.js';
import { APP_VERSION } from './version.js';
import { DEV_MODE_KEY, parseAppVersion, isNewVersion, resolveDevMode } from './version-check.js';

const DATA_STATUS_URL = 'shared/data-status.json';
const MEMBERS_URL = 'shared/vmforum_members.json';
const APP_VERSION_URL = 'app-version.json';

// Global variables
var map;
var markers;
var error_circle;
var layer_circles;
var form_select;
var form_search;
var search_suggestions;
var all_search_suggestions = [];
var active_search_suggestion = -1;
var search_suggestion_close_timer;
var member_update_timer;
var map_state_save_timer;
var map_state_save_promise = null;
var map_state_save_suspended = false;
var suppress_map_state_save_until = 0;
var last_location = null;
var location_layer;
var location_button;
var location_request_in_progress = false;

let members = [];
let dataStatus = null;
let dataSource = 'local';
let statusUi;
let cachedEtag = null;
let cachedLastModified = null;
let updateInProgress = false;
let update_reload_pending = false;
let keep_message_on_sync = false;

// Make the div element #map cover the whole window.
function resize_map_to_full_window()
{
	document.getElementById("map").style.position = "absolute";
	document.getElementById("map").style.left = "0px";
	document.getElementById("map").style.width = window.innerWidth + "px";
	document.getElementById("map").style.height = window.innerHeight + "px";
	document.getElementById("map").style.marginBottom = "0px";
}

function schedule_member_update() {
	clearTimeout(member_update_timer);
	member_update_timer = setTimeout(() => add_vmforum_members({ autoFit: true }), 0);
}

function apply_filter_search_to_url(search) {
	const url = new URL(window.location);
	for (const key of FILTER_PARAMS)
		url.searchParams.delete(key);
	for (const [key, value] of new URLSearchParams(search))
		url.searchParams.append(key, value);
	window.history.replaceState({}, '', url.href);
}

function schedule_map_state_save() {
	if (map_state_save_suspended)
		return;

	// Centering on the geolocation result must not persist the position via
	// the map center. Ignore the move/zoom events caused by that setView.
	if (Date.now() < suppress_map_state_save_until)
		return;

	clearTimeout(map_state_save_timer);
	map_state_save_timer = setTimeout(save_map_state, 300);
}

function suspend_map_state_save() {
	map_state_save_suspended = true;
	clearTimeout(map_state_save_timer);
	map_state_save_timer = null;
}

async function save_map_state() {
	clearTimeout(map_state_save_timer);
	map_state_save_timer = null;
	if (!map || map_state_save_suspended)
		return false;

	const pending = map_state_save_promise;
	if (pending)
		await pending.catch(() => {});
	if (map_state_save_suspended)
		return false;

	const center = map.getCenter();
	if (!shouldPersistMapState({
		center: [center.lat, center.lng],
		lastLocation: last_location,
		suspended: map_state_save_suspended,
	}))
		return false;

	map_state_save_promise = writeMapState({
		center: [center.lat, center.lng],
		zoom: map.getZoom(),
		search: filterSearchString(window.location.search),
	});
	try {
		return await map_state_save_promise;
	}
	finally {
		map_state_save_promise = null;
	}
}

async function clear_stored_map_filter() {
	const stored = await readMapState();
	if (stored)
		await writeMapState({ ...stored, search: '' });
}

async function reset_search() {
	if (!map)
		return;

	form_search.value = '';
	form_select.selectedIndex = 0;
	close_search_suggestions();

	const url = new URL(window.location);
	if (url.search) {
		url.search = '';
		window.history.replaceState({}, '', url.href);
	}

	add_vmforum_members({ autoFit: true });
	if (!(await save_map_state()))
		await clear_stored_map_filter();
}

async function deleteAppCaches() {
	const keys = await caches.keys();
	await Promise.all(keys
		.filter(key => key.startsWith('vmkarte-'))
		.map(key => caches.delete(key)));
}

async function clearAppCaches() {
	if ('serviceWorker' in navigator && navigator.serviceWorker.getRegistrations) {
		try {
			const registrations = await navigator.serviceWorker.getRegistrations();
			await Promise.all(registrations.map(registration => registration.unregister()));
		}
		catch (error) {
			console.warn('Service Worker konnte nicht abgemeldet werden.', error);
		}
	}

	if (!('caches' in window))
		return;

	try {
		await deleteAppCaches();
		// In-flight service worker handlers may recreate the cache after the
		// first delete. Give them a moment, then delete again.
		await new Promise(resolve => setTimeout(resolve, 100));
		await deleteAppCaches();
	}
	catch (error) {
		console.warn('App-Caches konnten nicht gelöscht werden.', error);
	}
}

async function logout() {
	suspend_map_state_save();
	try {
		if (map_state_save_promise)
			await map_state_save_promise.catch(() => {});
		await clearCache();
	}
	catch (e) {
		console.error(e);
	}
	await clearAppCaches();
	try {
		await fetch('/logout', {
			method: 'POST',
			credentials: 'same-origin',
			redirect: 'manual'
		});
	}
	catch (e) {
		console.error(e);
	}
	window.location.assign('/login');
}

async function handleUnauthorized() {
	suspend_map_state_save();
	try {
		if (map_state_save_promise)
			await map_state_save_promise.catch(() => {});
		await clearCache();
	}
	catch (error) {
		console.warn('Lokaler Kartenstand konnte nicht gelöscht werden.', error);
	}
	await clearAppCaches();
	const next = encodeURIComponent(window.location.pathname + window.location.search);
	window.location.assign('/login?next=' + next);
}

function show_update_message() {
	if (!statusUi)
		return;

	keep_message_on_sync = true;
	statusUi.setMessage({
		type: 'info',
		text: 'Eine neue Version ist verfügbar.',
		actionLabel: 'Neu laden',
		autoHideMs: 0,
		onRetry: request_update_reload,
	});
}

async function find_waiting_worker(timeoutMs = 3000) {
	if (!('serviceWorker' in navigator))
		return null;

	let registration;
	try {
		registration = await navigator.serviceWorker.getRegistration();
	}
	catch (error) {
		console.warn('Service Worker konnte nicht abgefragt werden.', error);
		return null;
	}
	if (!registration)
		return null;

	try {
		await registration.update();
	}
	catch (error) {
		console.warn('Service Worker konnte nicht aktualisiert werden.', error);
	}

	const end = Date.now() + timeoutMs;
	while (Date.now() < end) {
		if (registration.waiting)
			return registration.waiting;
		await new Promise(resolve => setTimeout(resolve, 100));
	}
	return registration.waiting || null;
}

async function request_update_reload() {
	if (update_reload_pending)
		return;
	update_reload_pending = true;

	const supports_service_worker = 'serviceWorker' in navigator;
	const reload_once = () => window.location.reload();
	if (supports_service_worker)
		navigator.serviceWorker.addEventListener('controllerchange', reload_once, { once: true });

	const waiting = await find_waiting_worker();
	if (!waiting) {
		if (supports_service_worker)
			navigator.serviceWorker.removeEventListener('controllerchange', reload_once);
		// Without a waiting worker, a plain reload could be served from the old
		// service worker cache. Clear it first so the reload really is fresh.
		await clearAppCaches();
		window.location.reload();
		return;
	}

	waiting.postMessage({ type: 'SKIP_WAITING' });
}

async function check_app_version() {
	try {
		const response = await fetch(APP_VERSION_URL, {
			cache: 'no-store',
			credentials: 'same-origin',
		});
		if (!response.ok)
			return;

		const remote = parseAppVersion(await response.json());
		if (!remote || !isNewVersion(APP_VERSION, remote.version))
			return;

		show_update_message();
	}
	catch (error) {
		console.warn('App-Version konnte nicht geprüft werden.', error);
	}
}

function read_dev_mode() {
	try {
		return sessionStorage.getItem(DEV_MODE_KEY);
	}
	catch (error) {
		console.warn('Entwicklungsmodus konnte nicht gelesen werden.', error);
		return null;
	}
}

function apply_dev_mode(devMode) {
	try {
		if (devMode.persist)
			sessionStorage.setItem(DEV_MODE_KEY, '1');
		else if (devMode.clear)
			sessionStorage.removeItem(DEV_MODE_KEY);
	}
	catch (error) {
		console.warn('Entwicklungsmodus konnte nicht gespeichert werden.', error);
	}
}

async function register_service_worker() {
	if (!('serviceWorker' in navigator))
		return;

	try {
		const registration = await navigator.serviceWorker.register('/service-worker.js');
		if (registration.waiting && navigator.serviceWorker.controller)
			show_update_message();

		registration.addEventListener('updatefound', () => {
			const worker = registration.installing;
			if (!worker)
				return;
			worker.addEventListener('statechange', () => {
				if (worker.state === 'installed' && navigator.serviceWorker.controller)
					show_update_message();
			});
		});
	}
	catch (error) {
		console.warn('Service Worker konnte nicht registriert werden.', error);
	}
}

function setRefreshBusy(busy) {
	const button = document.getElementById('refresh_button');
	if (!button)
		return;
	button.disabled = busy;
	button.classList.toggle('is-loading', busy);
	button.title = busy ? 'Kartendaten werden geladen …' : 'Kartendaten vom Server aktualisieren';
	button.setAttribute('aria-label', busy ? 'Kartendaten werden geladen' : 'Kartendaten aktualisieren');
}

function show_current_status(updateFailed = false) {
	if (!statusUi)
		return;
	if (members.length === 0) {
		statusUi.clearStatus();
		return;
	}
	statusUi.setStatus({
		generatedAt: dataStatus ? dataStatus.generatedAt : null,
		runStartedAt: dataStatus ? dataStatus.runStartedAt : null,
		source: dataSource,
		updateFailed,
		offline: navigator.onLine === false,
	});
}

async function loadDataStatus() {
	const response = await fetch(DATA_STATUS_URL, {
		cache: 'no-store',
		credentials: 'same-origin',
	});
	if (response.status === 401) {
		await handleUnauthorized();
		return { unauthorized: true, status: null };
	}
	if (!response.ok)
		throw new Error(`HTTP ${response.status}`);

	const raw = await response.json();
	return { unauthorized: false, status: parseDataStatus(raw) };
}

async function syncFromServer({ manual = false, autoFit = false } = {}) {
	if (updateInProgress)
		return;

	updateInProgress = true;
	setRefreshBusy(true);

	try {
		const statusResult = await loadDataStatus().catch(error => {
			console.warn('Datenstand konnte nicht geladen werden.', error);
			return { unauthorized: false, status: null };
		});
		if (statusResult.unauthorized)
			return;

		const headers = {};
		if (!manual && cachedEtag)
			headers['If-None-Match'] = cachedEtag;

		const response = await fetch(MEMBERS_URL, {
			cache: 'no-store',
			credentials: 'same-origin',
			headers,
		});

		if (response.status === 401) {
			await handleUnauthorized();
			return;
		}

		let membersChanged = false;
		if (response.status === 304) {
			// The locally stored member data is still current.
		}
		else if (response.ok) {
			const raw = await response.json();
			const validated = validateMembers(raw);
			if (!validated)
				throw new Error('Ungültige Mitgliederdaten');

			members = validated.members;
			membersChanged = true;
			cachedEtag = response.headers.get('ETag');
			cachedLastModified = response.headers.get('Last-Modified');
		}
		else {
			throw new Error(`HTTP ${response.status}`);
		}

		let serverStatus = statusResult.status;
		if (!serverStatus && cachedLastModified)
			serverStatus = deriveStatusFromLastModified(cachedLastModified, members.length);
		if (!serverStatus) {
			serverStatus = {
				generatedAt: new Date().toISOString(),
				runStartedAt: null,
				memberCount: members.length,
			};
		}

		dataStatus = serverStatus;
		dataSource = 'server';

		await writeCache({
			members,
			status: dataStatus,
			etag: cachedEtag,
			lastModified: cachedLastModified,
		});

		if (membersChanged) {
			add_vmforum_members({ autoFit });
			add_search_suggestions();
			log_member_stats();
		}

		if (members.length > 0) {
			show_current_status(false);
			if (!keep_message_on_sync)
				statusUi.clearMessage();
			if (manual && !keep_message_on_sync)
				statusUi.setMessage({ type: 'success', text: 'Kartendaten aktualisiert.' });
		}
	}
	catch (error) {
		console.warn('Serverabgleich fehlgeschlagen.', error);
		if (members.length > 0) {
			show_current_status(true);
			if (manual && !keep_message_on_sync) {
				statusUi.setMessage({
					type: 'error',
					text: 'Die Kartendaten konnten nicht aktualisiert werden. Der zuletzt geladene Stand bleibt sichtbar.',
				});
			}
		}
		else {
			statusUi.clearStatus();
			statusUi.setMessage({
				type: 'error',
				text: 'Die Kartendaten konnten nicht geladen werden. Bitte die Verbindung prüfen.',
				onRetry: () => syncFromServer({ manual: true }),
			});
		}
	}
	finally {
		updateInProgress = false;
		setRefreshBusy(false);
	}
}

function html_escape(str) {
	var tempDiv = document.createElement('div');
	tempDiv.textContent = str;
	return tempDiv.innerHTML;
}

function format_profile_date(value) {
	if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(value))
		return 'unbekannt';
	return value.slice(0, 10).split('-').reverse().join('.');
}

// Fill the suggestion list with search terms from names, vehicles and hashtags.
function add_search_suggestions() {
	all_search_suggestions = collectSearchSuggestions(members);
	if (!search_suggestions.hidden)
		render_search_suggestions();
}

function render_search_suggestions() {
	const values = filterSearchSuggestions(all_search_suggestions, form_search.value);
	active_search_suggestion = -1;
	search_suggestions.replaceChildren();

	if (values.length === 0) {
		close_search_suggestions();
		return;
	}

	const frag = document.createDocumentFragment();
	values.forEach((value, index) => {
		const option = document.createElement('li');
		option.id = `search_suggestion_${index}`;
		option.setAttribute('role', 'option');
		option.setAttribute('aria-selected', 'false');
		option.textContent = value;
		frag.appendChild(option);
	});

	search_suggestions.appendChild(frag);
	search_suggestions.hidden = false;
	form_search.setAttribute('aria-expanded', 'true');
	form_search.removeAttribute('aria-activedescendant');
}

function close_search_suggestions() {
	if (!search_suggestions)
		return;

	search_suggestions.hidden = true;
	search_suggestions.replaceChildren();
	active_search_suggestion = -1;
	form_search.setAttribute('aria-expanded', 'false');
	form_search.removeAttribute('aria-activedescendant');
}

function open_search_suggestions() {
	clearTimeout(search_suggestion_close_timer);
	render_search_suggestions();
}

function set_active_search_suggestion(index) {
	const options = search_suggestions.querySelectorAll('[role="option"]');
	if (options.length === 0)
		return;

	const next = (index + options.length) % options.length;
	options.forEach((option, optionIndex) => {
		option.setAttribute('aria-selected', optionIndex === next ? 'true' : 'false');
	});
	active_search_suggestion = next;
	form_search.setAttribute('aria-activedescendant', options[next].id);
	options[next].scrollIntoView({ block: 'nearest' });
}

function move_search_suggestion(direction) {
	if (search_suggestions.hidden)
		render_search_suggestions();
	if (search_suggestions.hidden)
		return;

	const count = search_suggestions.querySelectorAll('[role="option"]').length;
	if (count === 0)
		return;

	const index = active_search_suggestion < 0
		? (direction > 0 ? 0 : count - 1)
		: active_search_suggestion + direction;
	set_active_search_suggestion(index);
}

function sync_search_type(value, key) {
	if (/^#/.test(value))
		form_select.selectedIndex = 7;
	else if ((/^[^#]$/.test(value) && key !== 'Backspace' && key !== 'Delete')
		|| (/^[^#]/.test(value) && form_select.selectedIndex === 7))
		form_select.selectedIndex = 8;
}

function select_search_suggestion(value) {
	form_search.value = value;
	close_search_suggestions();
	sync_search_type(value, null);
	schedule_member_update();
}

function select_active_search_suggestion() {
	const option = search_suggestions.querySelectorAll('[role="option"]')[active_search_suggestion];
	if (option)
		select_search_suggestion(option.textContent);
}

function log_member_stats() {
	const timestamped_members = members.filter(v => v.profile_updated_at);
	console.log(`vmforum_members: ${timestamped_members.length}/${members.length} Einträge mit profile_updated_at`);
	if (timestamped_members.length === 0) {
		console.warn('Keine profile_updated_at-Werte geladen. Vermutlich wird eine alte vmforum_members.json ausgeliefert.');
	}
}

// Make markers not selectable by tab, since there are too many. The tooltip content can still be selected via tab.
function remove_tabindex() {
	Object
		.values(document.getElementsByClassName('leaflet-marker-icon'))
		.filter(v => v.tabIndex === 0)
		.forEach(v => v.tabIndex = -1);
}

function compute_search_center(points, zoom, size, preferredCenter) {
	const availableWidth = size.x - SEARCH_FIT_PADDING * 2;
	const availableHeight = size.y - SEARCH_FIT_PADDING * 2;
	const projectedPoints = points.map(point => map.project(L.latLng(point), zoom));
	const preferred = map.project(preferredCenter, zoom);
	const fitted = findClosestFittingCenter(
		projectedPoints,
		preferred,
		availableWidth,
		availableHeight,
	);

	return fitted ? map.unproject(L.point(fitted.x, fitted.y), zoom) : preferredCenter;
}

function fit_search_results(points) {
	if (!map || !Array.isArray(points) || points.length === 0)
		return;

	const validPoints = points.filter(point => Array.isArray(point)
		&& Number.isFinite(point[0])
		&& Number.isFinite(point[1]));
	if (validPoints.length === 0)
		return;

	const bounds = L.latLngBounds(validPoints);
	const size = map.getSize();
	const portrait = isPortraitSize(size.x, size.y);
	const singlePoint = bounds.getNorthEast().equals(bounds.getSouthWest());
	const targetZoom = clampSearchZoom(
		singlePoint
			? Number.POSITIVE_INFINITY
			: map.getBoundsZoom(bounds, false, L.point(SEARCH_FIT_PADDING * 2, SEARCH_FIT_PADDING * 2)),
		{ portrait },
	);

	if (!shouldAdjustSearchView({
		points: validPoints,
		currentBounds: map.getBounds(),
		currentZoom: map.getZoom(),
		targetZoom,
	}))
		return;

	const densestCenter = findDensestCenter(validPoints);
	const center = densestCenter
		? compute_search_center(validPoints, targetZoom, size, L.latLng(densestCenter))
		: bounds.getCenter();

	map.setView(center, targetZoom, { animate: false });
}

function add_vmforum_members({ autoFit = false } = {}) {

	// First, remove all members.
	map.eachLayer(l => (l instanceof L.MarkerClusterGroup) && map.removeLayer(l));

	// Clear the hashtag circles, and fill them again.
	layer_circles.clearLayers();

	// Get URL parameters.
	const urlparams = new URL(window.location).searchParams;

	// If there is a tag parameter, add it to the search for others (with # prepended).
	if (urlparams.has('tag') && urlparams.get('tag').match(HASHTAG_NAME_REGEX))
		urlparams.set('other', (urlparams.has('other') ? urlparams.get('other') + ' ' : '') + '#' + urlparams.get('tag'));

	// Look if we have a hashtag (take only the first one):
	// * If we a searching in the free-text field (bit 4 = other and bit 5 = search), look there.
	// * If there is an URL parameter 'other', look there.
	// * Otherwise, no hashtag possible.
	const found_tag = (form_select.value & (2**4 + 2**5))
		? form_search.value.match(HASHTAG_REGEX)
		: urlparams.has('other')
		? urlparams.get('other').match(HASHTAG_REGEX)
		: null;

	// Create a markerClusterGroup.
	markers = L
			// Cluster all markers within the given radius; by default, the radius is 80 px.
			// Instead use a user-defined function which decreases the radius with increasing zoom level.
			.markerClusterGroup({
				'maxClusterRadius': x => 40 - 3 * (map.getZoom() - 6),
				'zoomToBoundsOnClick': true
			})

			// When hovering with the mouse, show all markers of the cluster, but remove their tabindex.
			.on('clustermouseover', c => { c.layer.spiderfy(); remove_tabindex(); });

	// Create markers from the members array.
	const filtered_members = members
		// Filter 1: URL parameters
		// * Iterate over all properties.
		// * Exclude the member if any of the property checks fail (= the returned array from the inner filter has a non-zero length).
		// * The check fails if the URL parameter of the current property is set, but the current member does not have this property or the regex match (case insensitive) fails.
		// * The check succeeds if the property is not in the URL parameters or if the current member has this property and it matches the search if present.
		.filter(
			v => !['name', 'vm', 'lr', 'tr', 'other'].filter(n =>
				urlparams.has(n) && (
					!v[n] ||
					!v[n].match(RegExp(urlparams.get(n), 'i'))
				)
			).length
		)

		// Filter 2: input form (input field + dropdown button)
		// * Iterate over all properties.
		// * Include the member if any of the property checks succeed.
		// * The check succeeds if the bit of the dropdown value that corresponds to the current property is set and the current member has this property.
		// * If the search bit is set (bit 5), evaluate also the search (by matching the current property of the current member with the regex from the input field (case insensitive)).
		// * By default, the dropdown button has the value 1 which corresponds to the name property; since all members have names, this makes all members appear on the map.
		.filter(
			v => ['name', 'vm', 'lr', 'tr', 'other'].filter((n, i) =>
				(form_select.value & 2**i) &&
				v[n] &&
				(form_select.value & 2**5
					? v[n].match(RegExp(form_search.value, 'i'))
					: true
				)
			).length
		);

	const search_points = [];

	// Add a marker with popup to the markerClusterGroup for each remaining member.
	filtered_members.forEach( function(v) {
		search_points.push([Number(v.lat), Number(v.lon)]);
		markers.addLayer(
			L
			// Add the marker on the member’s address.
			.marker(
				[v.lat, v.lon],
				{
					// Set the name + bikes as tooltip (separate name and bikes with newline, separate bikes with comma, surround bike string with parentheses).
					'title': [
						html_escape(v.name),
						['vm', 'lr', 'tr']
							.filter(n => v[n])
							.map(n => html_escape(v[n]))
							.join(', ')
							.replace(/^.+$/, '($&)')
						].join('\n')
				})

			// Format the popup.
			.bindPopup(
				'<a href="https://www.velomobilforum.de/forum/index.php?members/'
				+ v.id
				+ '/" target="_blank" rel="noopener" title="Mitglieder-Profil im Forum"><b>'
				+ html_escape(v.name)
				+ '</b></a>'
				+ ' <a href="geo:' + v.lat + ',' + v.lon + '" title="Koordinaten, z.B. für BRouter">🌐</a>'
				+ (v.vm ? '<br /><b>Velomobil:</b> ' + html_escape(v.vm) : '')
				+ (v.lr ? '<br /><b>Liegerad:</b> ' + html_escape(v.lr) : '')
				+ (v.tr ? '<br /><b>Trike:</b> ' + html_escape(v.tr) : '')
				+ (v.other
					? '<br />' + html_escape(v.other).replace(HASHTAG_REGEX, match => '<a href="karte.html?other=' + encodeURIComponent(match) + '" title="alle mit diesem Hashtag anzeigen">' + match + '</a>')
					: '')
				+ '<br /><span class="stand" title="Letzter Profilabruf: '
				+ html_escape(v.profile_updated_at || 'unbekannt')
				+ '">Stand: ' + format_profile_date(v.profile_updated_at) + '</span>',
				{ 'closeOnEscapeKey': true }	// Seems to be broken.
				)
			// Close popup when Escape key is pressed.
			.on('keydown', e => e.originalEvent.key === 'Escape' && e.target.closePopup() )

			// When hovering over the marker, move the error circle there and set its radius;
			// when moving away, set stroke and fill to false.
			.on('mouseover', x => error_circle
						.setLatLng([v.lat, v.lon])
						.setRadius(v.radius)
						.setStyle({'stroke': true, 'fill': true}))
			.on('mouseout', x => error_circle
						.setStyle({'stroke': false, 'fill': false}))
		);

		// If a hashtag has been found, look if:
		// * the current member has it.
		// * it has a radius attached.
		// Then, add a circle.
		if (found_tag) {

			// Search for a radius after the hashtag, and add a circle if found.
			const tag_radius = v.other.match(RegExp(found_tag[0] + '=([0-9.]+)km', 'i'));
			if (tag_radius) {
				layer_circles.addLayer(
					L.circle([v.lat, v.lon],
					{
						'radius': tag_radius[1] * 1000,
						'className': 'tag_circle'
					}));
			}
		}
	});

	map.addLayer(markers);

	remove_tabindex();

	if (autoFit)
		fit_search_results(search_points);
}

function set_location_busy(busy) {
	if (!location_button)
		return;

	location_button.disabled = busy;
	location_button.classList.toggle('is-loading', busy);
	location_button.setAttribute('aria-busy', busy ? 'true' : 'false');

	const label = busy ? 'Standort wird ermittelt …' : 'Standort anzeigen';
	location_button.title = label;
	location_button.setAttribute('aria-label', label);
}

function show_position(position) {
	const { latitude, longitude, accuracy } = position.coords;

	// A pending save from before the click must not run after the map has
	// been centered on the location.
	clearTimeout(map_state_save_timer);
	map_state_save_timer = null;
	last_location = [latitude, longitude];

	if (!location_layer)
		location_layer = L.layerGroup().addTo(map);
	location_layer.clearLayers();

	L.circleMarker([latitude, longitude], {
		radius: 7,
		color: '#fff',
		weight: 2,
		fillColor: '#1565c0',
		fillOpacity: 1,
		className: 'location-marker',
	}).addTo(location_layer);

	if (Number.isFinite(accuracy) && accuracy > 0) {
		L.circle([latitude, longitude], {
			radius: accuracy,
			color: '#1565c0',
			weight: 1,
			fillColor: '#1565c0',
			fillOpacity: 0.12,
			className: 'location-accuracy',
		}).addTo(location_layer);
	}

	suppress_map_state_save_until = Date.now() + 1000;
	map.setView([latitude, longitude], Math.max(map.getZoom(), 14));
}

function request_location() {
	if (location_request_in_progress)
		return;

	if (!navigator.geolocation) {
		statusUi.setMessage({ type: 'error', text: 'Dieser Browser unterstützt keine Standortbestimmung.' });
		return;
	}

	location_request_in_progress = true;
	set_location_busy(true);

	const handle_error = error => {
		location_request_in_progress = false;
		set_location_busy(false);
		statusUi.setMessage({ type: 'error', text: describeGeolocationError(error) });
	};

	try {
		navigator.geolocation.getCurrentPosition(
			position => {
				location_request_in_progress = false;
				set_location_busy(false);
				show_position(position);
			},
			handle_error,
			GEOLOCATION_OPTIONS,
		);
	}
	catch (error) {
		handle_error(error);
	}
}

async function create_map() {
	statusUi = createStatusUi({
		statusElement: document.getElementById('data_status'),
		messageElement: document.getElementById('data_message'),
		offlineElement: document.getElementById('offline_badge'),
	});

	const devMode = resolveDevMode(window.location.search, read_dev_mode());
	apply_dev_mode(devMode);

	// Install protocol handler for geo: protocol; must be a local script, which reformats the coordinates and redirects to BRouter
	try {
		window.navigator.registerProtocolHandler('geo', '/geo-handler?l=%s', 'BRouter-Web');
	}
	catch (e) {
		console.error(e)
	}

	form_select = document.getElementById('form_select');
	form_search = document.getElementById('form_search');
	search_suggestions = document.getElementById('search_suggestions');
	location_button = document.getElementById('location_button');

	L.DomEvent.on(document.getElementById('reset_button'), 'click', reset_search);
	L.DomEvent.on(document.getElementById('logout_button'), 'click', logout);

	// Make the map container cover the whole browser window.
	resize_map_to_full_window();

	const [cache, storedMapState] = await Promise.all([
		readCache().catch(error => {
			console.warn('Lokaler Kartenstand konnte nicht gelesen werden.', error);
			return null;
		}),
		readMapState().catch(error => {
			console.warn('Lokaler Kartenstatus konnte nicht gelesen werden.', error);
			return null;
		}),
	]);

	const autoFitInitial = filterSearchString(window.location.search).length > 0;
	const initialMapState = resolveInitialMapState({
		urlSearch: window.location.search,
		stored: storedMapState,
	});
	if (initialMapState.applyStoredSearch)
		apply_filter_search_to_url(initialMapState.search);

	// Form inputs always start at their defaults; filters come from the URL.
	form_search.value = '';
	form_select.selectedIndex = 0;

	// Create map, without animations but with OSM/Nominatim attribution.
	map = L.map('map', {
		'zoomAnimation': false,
		'fadeAnimation': false,

		// Use Openstreetmap as tile layer.
		}).addLayer(
			L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
				'attribution': '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>-Mitwirkende, <a href="https://opendatacommons.org/licenses/odbl/1-0/" target="_blank" rel="noopener">ODbL</a>',
				'useCache': true
			})

		// Restore the last map view, or fall back to Germany.
		).setView(initialMapState.center, initialMapState.zoom);

	map.attributionControl.addAttribution(
		'Geocoding: <a href="https://nominatim.org/" target="_blank" rel="noopener">Nominatim</a>'
	);

	// Add the input form as a Leaflet control into the top right corner.
	const search_controls = document.getElementById('search_controls');
	const search_control = new L.Control({ position: 'topright'});
	search_control.onAdd = map => search_controls;
	search_control.addTo(map);
	L.DomEvent.disableClickPropagation(search_controls);
	L.DomEvent.disableScrollPropagation(search_controls);

	// Update the markers immediately when the filter dropdown changes; a
	// suggestion pick is handled by select_search_suggestion().
	form_select.addEventListener('input', schedule_member_update);
	form_select.addEventListener('change', schedule_member_update);
	form_search.addEventListener('change', schedule_member_update);

	form_search.addEventListener('focus', open_search_suggestions);
	form_search.addEventListener('blur', () => {
		clearTimeout(search_suggestion_close_timer);
		search_suggestion_close_timer = setTimeout(close_search_suggestions, 200);
	});

	form_search.addEventListener('input', () => {
		render_search_suggestions();
		if (all_search_suggestions.includes(form_search.value))
			schedule_member_update();
	});

	search_suggestions.addEventListener('pointerdown', e => {
		clearTimeout(search_suggestion_close_timer);
		if (e.pointerType === 'mouse')
			e.preventDefault();
	});

	search_suggestions.addEventListener('click', e => {
		const option = e.target.closest('[role="option"]');
		if (option)
			select_search_suggestion(option.textContent);
	});

	L.DomEvent.on(form_search, 'keydown', function(e) {
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			e.preventDefault();
			move_search_suggestion(e.key === 'ArrowDown' ? 1 : -1);
			return;
		}

		if (e.key === 'Escape') {
			close_search_suggestions();
			return;
		}

		if (e.key === 'Enter') {
			if (!search_suggestions.hidden && active_search_suggestion >= 0) {
				select_active_search_suggestion();
				return;
			}
			close_search_suggestions();
			add_vmforum_members({ autoFit: true });
		}
	});

	// Switch search type, but only after key is released, when the value has been updated.
	L.DomEvent.on(form_search, 'keyup', function(e) {
		sync_search_type(form_search.value, e.key);
	});

	// Add a layerGroup for all hashtag circles; empty at the beginning.
	layer_circles = L.layerGroup();
	map.addLayer(layer_circles);

	// A circle showing the size of the bounding box given by Nominatim.
	// Create only one circle and move it to the current marker.
	error_circle = L.circle([0, 0], { stroke: false, fill: false }).addTo(map);

	document.getElementById('refresh_button').addEventListener('click', () => {
		syncFromServer({ manual: true });
		if (!devMode.enabled)
			check_app_version();
	});

	if (location_button)
		L.DomEvent.on(location_button, 'click', request_location);
	map.on('moveend zoomend', schedule_map_state_save);

	if (cache && cache.members.length > 0) {
		members = cache.members;
		dataStatus = cache.status;
		dataSource = 'local';
		cachedEtag = cache.etag;
		cachedLastModified = cache.lastModified;

		add_vmforum_members({ autoFit: autoFitInitial });
		add_search_suggestions();
		log_member_stats();
		show_current_status(false);
		statusUi.clearMessage();
	}
	else {
		statusUi.clearStatus();
		statusUi.setMessage({ type: 'loading', text: 'Kartendaten werden geladen …' });
	}

	function update_online_state() {
		const offline = navigator.onLine === false;
		statusUi.setOffline(offline);
		if (offline)
			show_current_status(false);
	}

	window.addEventListener('offline', update_online_state);
	window.addEventListener('online', () => {
		update_online_state();
		syncFromServer();
		if (!devMode.enabled)
			check_app_version();
	});
	update_online_state();

	if (devMode.enabled) {
		await clearAppCaches();
		keep_message_on_sync = true;
		statusUi.setMessage({
			type: 'info',
			text: 'Entwicklungsmodus aktiv: Service Worker und App-Caches sind deaktiviert.',
			autoHideMs: 6000,
		});
	}

	syncFromServer({
		autoFit: autoFitInitial && !(cache && cache.members.length > 0),
	});

	if (!devMode.enabled) {
		register_service_worker();
		check_app_version();
	}

	// Add the accessKey of the element to its tooltip.
	Object
		.values(document.getElementsByTagName('*'))
		.filter(v => v.accessKey)
		.forEach(v => v.title += '\n[' + (v.accessKeyLabel ? v.accessKeyLabel : 'Taste: ' + v.accessKey) + ']');
}

document.addEventListener('DOMContentLoaded', create_map);
window.addEventListener('resize', function() {
	resize_map_to_full_window();
	if (map) map.invalidateSize();
});
