export const DEFAULT_MAP_VIEW = Object.freeze({
	center: Object.freeze([50, 11]),
	zoom: 7,
});

export const FILTER_PARAMS = Object.freeze(['name', 'vm', 'lr', 'tr', 'other', 'tag']);
export const LOCATION_TOLERANCE_DEGREES = 0.0001;

function toFiniteNumber(value) {
	if (typeof value === 'number')
		return Number.isFinite(value) ? value : null;
	if (typeof value === 'string' && value.trim() !== '') {
		const number = Number(value);
		return Number.isFinite(number) ? number : null;
	}
	return null;
}

export function filterSearchString(search) {
	if (typeof search !== 'string' || search.length === 0)
		return '';

	const input = new URLSearchParams(search);
	const output = new URLSearchParams();
	for (const key of FILTER_PARAMS) {
		for (const value of input.getAll(key))
			output.append(key, value);
	}
	return output.toString();
}

export function parseMapState(raw) {
	if (!raw || typeof raw !== 'object' || Array.isArray(raw))
		return null;

	const { center, zoom, search } = raw;
	if (!Array.isArray(center) || center.length !== 2)
		return null;

	const lat = toFiniteNumber(center[0]);
	const lon = toFiniteNumber(center[1]);
	if (lat === null || lon === null || lat < -90 || lat > 90
		|| lon < -180 || lon > 180)
		return null;

	const numericZoom = toFiniteNumber(zoom);
	if (numericZoom === null || numericZoom < 0 || numericZoom > 22)
		return null;

	if (search != null && typeof search !== 'string')
		return null;

	return {
		center: [lat, lon],
		zoom: numericZoom,
		search: filterSearchString(search ?? ''),
	};
}

export function isSamePosition(center, other, tolerance = LOCATION_TOLERANCE_DEGREES) {
	if (!Array.isArray(center) || !Array.isArray(other)
		|| center.length !== 2 || other.length !== 2)
		return false;

	const lat1 = toFiniteNumber(center[0]);
	const lon1 = toFiniteNumber(center[1]);
	const lat2 = toFiniteNumber(other[0]);
	const lon2 = toFiniteNumber(other[1]);
	if (lat1 === null || lon1 === null || lat2 === null || lon2 === null)
		return false;

	return Math.abs(lat1 - lat2) <= tolerance && Math.abs(lon1 - lon2) <= tolerance;
}

export function shouldPersistMapState({ center, lastLocation = null, suspended = false } = {}) {
	if (suspended)
		return false;
	if (lastLocation && isSamePosition(center, lastLocation))
		return false;
	return true;
}

export function resolveInitialMapState({ urlSearch = '', stored = null, defaultView = DEFAULT_MAP_VIEW } = {}) {
	const parsedStored = parseMapState(stored);
	const urlFilters = filterSearchString(urlSearch);
	const storedFilters = parsedStored ? parsedStored.search : '';
	const search = urlFilters || storedFilters;

	return {
		center: parsedStored ? [...parsedStored.center] : [...defaultView.center],
		zoom: parsedStored ? parsedStored.zoom : defaultView.zoom,
		search,
		applyStoredSearch: !urlFilters && storedFilters.length > 0,
	};
}
