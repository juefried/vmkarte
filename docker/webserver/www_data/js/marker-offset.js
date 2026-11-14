export const MARKER_OFFSET_MIN_COUNT = 2;
export const MARKER_OFFSET_ARC_SPACING_PX = 18;
export const MARKER_OFFSET_RING_STEP_PX = 18;
export const MARKER_OFFSET_MAX_METERS = 100;

const EARTH_CIRCUMFERENCE_METERS = 40075016.686;
const TILE_SIZE = 256;
const METERS_PER_PIXEL_AT_ZOOM_0 = EARTH_CIRCUMFERENCE_METERS / TILE_SIZE;
const MAX_LATITUDE = 85.0511287798;

function toFiniteNumber(value) {
	if (typeof value === 'number')
		return Number.isFinite(value) ? value : null;
	if (typeof value === 'string' && value.trim() !== '') {
		const number = Number(value);
		return Number.isFinite(number) ? number : null;
	}
	return null;
}

function positiveNumber(value, fallback) {
	return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function metersPerPixel(latitude, zoom) {
	if (!Number.isFinite(latitude) || !Number.isFinite(zoom))
		return null;

	const latitudeScale = Math.max(0.01, Math.abs(Math.cos(latitude * Math.PI / 180)));
	return METERS_PER_PIXEL_AT_ZOOM_0 * latitudeScale / (2 ** zoom);
}

export function offsetScaleForZoom({
	latitude,
	zoom,
	maxRadiusPixels,
	maxMeters = MARKER_OFFSET_MAX_METERS,
} = {}) {
	if (!Number.isFinite(maxRadiusPixels) || maxRadiusPixels <= 0
		|| !Number.isFinite(maxMeters) || maxMeters <= 0)
		return 0;

	const metersPerPixelValue = metersPerPixel(latitude, zoom);
	if (!Number.isFinite(metersPerPixelValue) || metersPerPixelValue <= 0)
		return 0;

	const allowedPixelRadius = maxMeters / metersPerPixelValue;
	return Math.min(1, Math.max(0, allowedPixelRadius / maxRadiusPixels));
}

export function offsetLatLng({ lat, lon, dx = 0, dy = 0, zoom } = {}) {
	if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(zoom))
		return null;

	const clampedLat = Math.min(MAX_LATITUDE, Math.max(-MAX_LATITUDE, lat));
	const worldSize = TILE_SIZE * (2 ** zoom);
	const sinLat = Math.sin(clampedLat * Math.PI / 180);
	const x = (lon + 180) / 360 * worldSize;
	const y = (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * worldSize;
	const nextX = x + dx;
	const nextY = y + dy;
	const nextLon = nextX / worldSize * 360 - 180;
	const nextLat = Math.atan(Math.sinh(Math.PI * (1 - 2 * nextY / worldSize))) * 180 / Math.PI;

	if (!Number.isFinite(nextLat) || !Number.isFinite(nextLon))
		return null;

	return [nextLat, nextLon];
}

export function groupDuplicateMarkers(members) {
	if (!Array.isArray(members))
		return [];

	const groups = new Map();

	members.forEach((member, index) => {
		const lat = toFiniteNumber(member && member.lat);
		const lon = toFiniteNumber(member && member.lon);
		if (lat === null || lon === null || lat < -90 || lat > 90 || lon < -180 || lon > 180)
			return;

		const key = `${lat}|${lon}`;
		let group = groups.get(key);
		if (!group) {
			group = { key, lat, lon, indexes: [] };
			groups.set(key, group);
		}
		group.indexes.push(index);
	});

	return [...groups.values()]
		.filter(group => group.indexes.length >= MARKER_OFFSET_MIN_COUNT);
}

export function computeOffsetPixels(count, {
	arcSpacing = MARKER_OFFSET_ARC_SPACING_PX,
	ringStep = MARKER_OFFSET_RING_STEP_PX,
} = {}) {
	const normalizedCount = Number.isFinite(count) ? Math.max(0, Math.floor(count)) : 0;
	if (normalizedCount === 0)
		return [];
	if (normalizedCount === 1)
		return [{ x: 0, y: 0 }];

	const spacing = positiveNumber(arcSpacing, MARKER_OFFSET_ARC_SPACING_PX);
	const step = positiveNumber(ringStep, MARKER_OFFSET_RING_STEP_PX);
	const offsets = [];
	let remaining = normalizedCount;
	let radius = step;
	let ringIndex = 0;

	while (remaining > 0) {
		const capacity = Math.max(1, Math.floor((2 * Math.PI * radius) / spacing));
		const slots = Math.min(capacity, remaining);
		const startAngle = -Math.PI / 2 + (ringIndex % 2) * (Math.PI / slots);

		for (let index = 0; index < slots; index++) {
			const angle = startAngle + (2 * Math.PI * index) / slots;
			offsets.push({
				x: Math.cos(angle) * radius,
				y: Math.sin(angle) * radius,
			});
		}

		remaining -= slots;
		radius += step;
		ringIndex++;
	}

	return offsets;
}

export function maxOffsetRadius(offsets) {
	if (!Array.isArray(offsets) || offsets.length === 0)
		return 0;

	return offsets.reduce((maximum, offset) => {
		if (!offset || !Number.isFinite(offset.x) || !Number.isFinite(offset.y))
			return maximum;
		return Math.max(maximum, Math.hypot(offset.x, offset.y));
	}, 0);
}
