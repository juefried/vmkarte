export const SEARCH_FIT_MIN_ZOOM_PORTRAIT = 5;
export const SEARCH_FIT_MIN_ZOOM_LANDSCAPE = 5;
export const SEARCH_FIT_MAX_ZOOM_PORTRAIT = 13;
export const SEARCH_FIT_MAX_ZOOM_LANDSCAPE = 15;
export const SEARCH_FIT_ZOOM_TOLERANCE = 2;
export const SEARCH_FIT_PADDING = 40;
export const SEARCH_FIT_RADIUS_PERCENTILE = 0.75;
export const SEARCH_FIT_RADIUS_MAX_VISIBLE_PINS = 5;

const GRID_DIVISIONS = 20;
const EPSILON = 1e-9;
const EARTH_CIRCUMFERENCE_METERS = 40075016.686;
const TILE_SIZE = 256;
const METERS_PER_PIXEL_AT_ZOOM_0 = EARTH_CIRCUMFERENCE_METERS / TILE_SIZE;

function normalizePoints(points) {
	if (!Array.isArray(points))
		return [];

	return points
		.filter(point => Array.isArray(point)
			&& point.length === 2
			&& Number.isFinite(point[0])
			&& Number.isFinite(point[1])
			&& point[0] >= -90
			&& point[0] <= 90
			&& point[1] >= -180
			&& point[1] <= 180)
		.map(point => [point[0], point[1]]);
}

function getBoundsEdges(bounds) {
	if (!bounds || typeof bounds !== 'object')
		return null;

	const south = Number.isFinite(bounds.south) ? bounds.south
		: typeof bounds.getSouth === 'function' ? bounds.getSouth() : null;
	const west = Number.isFinite(bounds.west) ? bounds.west
		: typeof bounds.getWest === 'function' ? bounds.getWest() : null;
	const north = Number.isFinite(bounds.north) ? bounds.north
		: typeof bounds.getNorth === 'function' ? bounds.getNorth() : null;
	const east = Number.isFinite(bounds.east) ? bounds.east
		: typeof bounds.getEast === 'function' ? bounds.getEast() : null;

	if (![south, west, north, east].every(Number.isFinite))
		return null;

	return { south, west, north, east };
}

export function isPortraitSize(width, height) {
	return Number.isFinite(width) && Number.isFinite(height) && height > width;
}

export function hasAnyPointInBounds(points, bounds) {
	const validPoints = normalizePoints(points);
	if (validPoints.length === 0 || !bounds)
		return false;

	if (typeof bounds.contains === 'function')
		return validPoints.some(point => bounds.contains(point));

	const edges = getBoundsEdges(bounds);
	if (!edges)
		return false;

	return validPoints.some(([lat, lon]) => lat >= edges.south
		&& lat <= edges.north
		&& lon >= edges.west
		&& lon <= edges.east);
}

export function clampSearchZoom(fitZoom, { portrait = false, maxZoom = null } = {}) {
	const minZoom = portrait
		? SEARCH_FIT_MIN_ZOOM_PORTRAIT
		: SEARCH_FIT_MIN_ZOOM_LANDSCAPE;
	const orientationMaxZoom = portrait
		? SEARCH_FIT_MAX_ZOOM_PORTRAIT
		: SEARCH_FIT_MAX_ZOOM_LANDSCAPE;
	const effectiveMaxZoom = Math.max(
		minZoom,
		Number.isFinite(maxZoom) ? Math.min(orientationMaxZoom, maxZoom) : orientationMaxZoom,
	);

	if (!Number.isFinite(fitZoom))
		return effectiveMaxZoom;

	return Math.min(effectiveMaxZoom, Math.max(minZoom, fitZoom));
}

export function zoomForRadius(radiusMeters, latitude, viewportMinDimension, padding = SEARCH_FIT_PADDING) {
	if (!Number.isFinite(radiusMeters) || radiusMeters <= 0
		|| !Number.isFinite(latitude)
		|| !Number.isFinite(viewportMinDimension)
		|| !Number.isFinite(padding))
		return null;

	const availablePixelRadius = (viewportMinDimension - padding * 2) / 2;
	if (availablePixelRadius <= 0)
		return null;

	const latitudeScale = Math.max(0.01, Math.abs(Math.cos(latitude * Math.PI / 180)));
	const metersPerPixelAtZoom0 = METERS_PER_PIXEL_AT_ZOOM_0 * latitudeScale;
	const exactZoom = Math.log2(metersPerPixelAtZoom0 * availablePixelRadius / radiusMeters);

	return Math.floor(exactZoom);
}

export function radiusZoomLimit(results, {
	percentile = SEARCH_FIT_RADIUS_PERCENTILE,
	viewportMinDimension,
	padding = SEARCH_FIT_PADDING,
} = {}) {
	if (!Array.isArray(results) || !Number.isFinite(viewportMinDimension))
		return null;

	const limits = results
		.map(result => result && zoomForRadius(result.radius, result.lat, viewportMinDimension, padding))
		.filter(limit => limit !== null)
		.sort((a, b) => a - b);

	if (limits.length === 0)
		return null;

	const normalizedPercentile = Number.isFinite(percentile)
		? Math.min(1, Math.max(0, percentile))
		: SEARCH_FIT_RADIUS_PERCENTILE;
	const index = Math.min(
		limits.length - 1,
		Math.floor((1 - normalizedPercentile) * limits.length),
	);

	return limits[index];
}

export function isPointInView(point, center, availableWidth, availableHeight) {
	if (!point || !center
		|| !Number.isFinite(point.x) || !Number.isFinite(point.y)
		|| !Number.isFinite(center.x) || !Number.isFinite(center.y)
		|| !Number.isFinite(availableWidth) || !Number.isFinite(availableHeight))
		return false;

	return Math.abs(point.x - center.x) <= availableWidth / 2
		&& Math.abs(point.y - center.y) <= availableHeight / 2;
}

export function countPointsInView(points, center, availableWidth, availableHeight) {
	if (!Array.isArray(points))
		return 0;

	return points.filter(point => isPointInView(point, center, availableWidth, availableHeight)).length;
}

export function findClosestFittingCenter(points, preferred, availableWidth, availableHeight) {
	if (!Array.isArray(points) || points.length === 0
		|| !preferred
		|| !Number.isFinite(preferred.x)
		|| !Number.isFinite(preferred.y)
		|| !Number.isFinite(availableWidth)
		|| !Number.isFinite(availableHeight)
		|| availableWidth <= 0
		|| availableHeight <= 0)
		return null;

	let minX = Infinity;
	let maxX = -Infinity;
	let minY = Infinity;
	let maxY = -Infinity;

	for (const point of points) {
		if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y))
			return null;
		minX = Math.min(minX, point.x);
		maxX = Math.max(maxX, point.x);
		minY = Math.min(minY, point.y);
		maxY = Math.max(maxY, point.y);
	}

	if (maxX - minX > availableWidth || maxY - minY > availableHeight)
		return null;

	const x = Math.min(
		minX + availableWidth / 2,
		Math.max(maxX - availableWidth / 2, preferred.x),
	);
	const y = Math.min(
		minY + availableHeight / 2,
		Math.max(maxY - availableHeight / 2, preferred.y),
	);

	return { x, y };
}

export function findDensestCenter(points) {
	const validPoints = normalizePoints(points);
	if (validPoints.length === 0)
		return null;
	if (validPoints.length === 1)
		return [...validPoints[0]];

	let minLat = Infinity;
	let maxLat = -Infinity;
	let minLon = Infinity;
	let maxLon = -Infinity;

	for (const [lat, lon] of validPoints) {
		minLat = Math.min(minLat, lat);
		maxLat = Math.max(maxLat, lat);
		minLon = Math.min(minLon, lon);
		maxLon = Math.max(maxLon, lon);
	}

	const spanLat = maxLat - minLat;
	const spanLon = maxLon - minLon;
	if (spanLat < EPSILON && spanLon < EPSILON)
		return [...validPoints[0]];

	const midLat = (minLat + maxLat) / 2;
	const lonScale = Math.max(0.01, Math.abs(Math.cos(midLat * Math.PI / 180)));

	const cells = new Map();
	for (const [lat, lon] of validPoints) {
		const x = spanLon < EPSILON ? 0.5 : (lon - minLon) / spanLon;
		const y = spanLat < EPSILON ? 0.5 : (lat - minLat) / spanLat;
		const cellX = Math.min(GRID_DIVISIONS - 1, Math.max(0, Math.floor(x * GRID_DIVISIONS)));
		const cellY = Math.min(GRID_DIVISIONS - 1, Math.max(0, Math.floor(y * GRID_DIVISIONS)));
		const key = `${cellX}:${cellY}`;

		let cell = cells.get(key);
		if (!cell) {
			cell = { count: 0, latSum: 0, lonSum: 0, cellX, cellY };
			cells.set(key, cell);
		}
		cell.count++;
		cell.latSum += lat;
		cell.lonSum += lon;
	}

	const centerLat = (minLat + maxLat) / 2;
	const centerLon = (minLon + maxLon) / 2;
	let bestCell = null;
	let bestDistance = Infinity;

	for (const cell of cells.values()) {
		const lat = cell.latSum / cell.count;
		const lon = cell.lonSum / cell.count;
		const distance = ((lat - centerLat) * (lat - centerLat))
			+ (((lon - centerLon) * lonScale) * ((lon - centerLon) * lonScale));

		if (!bestCell
			|| cell.count > bestCell.count
			|| (cell.count === bestCell.count && distance < bestDistance)) {
			bestCell = cell;
			bestDistance = distance;
		}
	}

	return [bestCell.latSum / bestCell.count, bestCell.lonSum / bestCell.count];
}

export function shouldAdjustSearchView({
	points,
	currentBounds,
	currentZoom,
	targetZoom,
} = {}) {
	const validPoints = normalizePoints(points);
	if (validPoints.length === 0)
		return false;

	if (!hasAnyPointInBounds(validPoints, currentBounds))
		return true;

	if (!Number.isFinite(currentZoom) || !Number.isFinite(targetZoom))
		return false;

	return currentZoom <= targetZoom - SEARCH_FIT_ZOOM_TOLERANCE;
}
