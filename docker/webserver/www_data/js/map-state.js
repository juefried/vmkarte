export const DEFAULT_MAP_VIEW = Object.freeze({
	center: Object.freeze([50, 11]),
	zoom: 7,
});

export const FILTER_PARAMS = Object.freeze(['name', 'vm', 'lr', 'tr', 'other', 'tag']);

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

	const lat = Number(center[0]);
	const lon = Number(center[1]);
	if (!Number.isFinite(lat) || lat < -90 || lat > 90
		|| !Number.isFinite(lon) || lon < -180 || lon > 180)
		return null;

	const numericZoom = Number(zoom);
	if (!Number.isFinite(numericZoom) || numericZoom < 0 || numericZoom > 22)
		return null;

	if (search != null && typeof search !== 'string')
		return null;

	return {
		center: [lat, lon],
		zoom: numericZoom,
		search: filterSearchString(search ?? ''),
	};
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
