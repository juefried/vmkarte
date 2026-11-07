import test from 'node:test';
import assert from 'node:assert/strict';

import {
	SEARCH_FIT_MAX_ZOOM_LANDSCAPE,
	SEARCH_FIT_MAX_ZOOM_PORTRAIT,
	SEARCH_FIT_MIN_ZOOM,
	SEARCH_FIT_ZOOM_TOLERANCE,
	clampSearchZoom,
	findDensestCenter,
	hasAnyPointInBounds,
	isPortraitSize,
	shouldAdjustSearchView,
} from '../../docker/webserver/www_data/js/search-fit.js';

test('findDensestCenter returns the center of the largest cluster', () => {
	const center = findDensestCenter([
		[52.5, 13.4],
		[52.51, 13.41],
		[52.52, 13.42],
		[48, 9],
	]);

	assert.ok(Math.abs(center[0] - 52.51) < 1e-9);
	assert.ok(Math.abs(center[1] - 13.41) < 1e-9);
});

test('findDensestCenter handles empty, single and identical points', () => {
	assert.equal(findDensestCenter([]), null);
	assert.deepEqual(findDensestCenter([[50, 11]]), [50, 11]);
	assert.deepEqual(findDensestCenter([[50, 11], [50, 11], [50, 11]]), [50, 11]);
});

test('findDensestCenter ignores invalid coordinates', () => {
	assert.deepEqual(
		findDensestCenter([
			[50, 11],
			[null, 11],
			['50', '11'],
			[95, 11],
			[51, 12],
			[51, 12],
		]),
		[51, 12],
	);
});

test('hasAnyPointInBounds supports Leaflet-style bounds objects', () => {
	const bounds = {
		contains: ([lat, lon]) => lat >= 40 && lat <= 60 && lon >= 5 && lon <= 15,
	};

	assert.equal(hasAnyPointInBounds([[50, 10]], bounds), true);
	assert.equal(hasAnyPointInBounds([[70, 10]], bounds), false);
	assert.equal(hasAnyPointInBounds([], bounds), false);
});

test('hasAnyPointInBounds supports plain edge objects inclusively', () => {
	const bounds = { south: 40, west: 5, north: 60, east: 15 };

	assert.equal(hasAnyPointInBounds([[40, 5]], bounds), true);
	assert.equal(hasAnyPointInBounds([[60, 15]], bounds), true);
	assert.equal(hasAnyPointInBounds([[39.99, 10]], bounds), false);
	assert.equal(hasAnyPointInBounds([[50, 15.01]], bounds), false);
});

test('clampSearchZoom applies the minimum and orientation-dependent maximum', () => {
	assert.equal(clampSearchZoom(10), 10);
	assert.equal(clampSearchZoom(2), SEARCH_FIT_MIN_ZOOM);
	assert.equal(
		clampSearchZoom(18, { portrait: true }),
		SEARCH_FIT_MAX_ZOOM_PORTRAIT,
	);
	assert.equal(
		clampSearchZoom(18, { portrait: false }),
		SEARCH_FIT_MAX_ZOOM_LANDSCAPE,
	);
	assert.equal(
		clampSearchZoom(Number.POSITIVE_INFINITY, { portrait: true }),
		SEARCH_FIT_MAX_ZOOM_PORTRAIT,
	);
});

test('isPortraitSize detects portrait viewports', () => {
	assert.equal(isPortraitSize(400, 800), true);
	assert.equal(isPortraitSize(800, 400), false);
	assert.equal(isPortraitSize(500, 500), false);
	assert.equal(isPortraitSize(Number.NaN, 500), false);
});

test('shouldAdjustSearchView fits when no result pin is visible', () => {
	const currentBounds = { south: 0, west: 0, north: 1, east: 1 };

	assert.equal(shouldAdjustSearchView({
		points: [[50, 11]],
		currentBounds,
		currentZoom: 13,
		targetZoom: 13,
	}), true);
});

test('shouldAdjustSearchView zooms in when the view is too far out', () => {
	const currentBounds = { south: 40, west: 5, north: 60, east: 15 };
	const targetZoom = 13;
	const currentZoom = targetZoom - SEARCH_FIT_ZOOM_TOLERANCE;

	assert.equal(shouldAdjustSearchView({
		points: [[50, 10]],
		currentBounds,
		currentZoom,
		targetZoom,
	}), true);
});

test('shouldAdjustSearchView leaves an approximately fitting view alone', () => {
	const currentBounds = { south: 40, west: 5, north: 60, east: 15 };

	assert.equal(shouldAdjustSearchView({
		points: [[50, 10]],
		currentBounds,
		currentZoom: 12,
		targetZoom: 13,
	}), false);
	assert.equal(shouldAdjustSearchView({
		points: [[50, 10]],
		currentBounds,
		currentZoom: 14,
		targetZoom: 13,
	}), false);
});

test('shouldAdjustSearchView ignores empty result sets', () => {
	assert.equal(shouldAdjustSearchView({
		points: [],
		currentBounds: { south: 0, west: 0, north: 1, east: 1 },
		currentZoom: 10,
		targetZoom: 13,
	}), false);
});
