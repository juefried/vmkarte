import test from 'node:test';
import assert from 'node:assert/strict';

import {
	SEARCH_FIT_MAX_ZOOM_LANDSCAPE,
	SEARCH_FIT_MAX_ZOOM_PORTRAIT,
	SEARCH_FIT_MIN_ZOOM_LANDSCAPE,
	SEARCH_FIT_MIN_ZOOM_PORTRAIT,
	SEARCH_FIT_ZOOM_TOLERANCE,
	clampSearchZoom,
	countPointsInView,
	findClosestFittingCenter,
	findDensestCenter,
	hasAnyPointInBounds,
	isPointInView,
	isPortraitSize,
	radiusZoomLimit,
	shouldAdjustSearchView,
	zoomForRadius,
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

test('clampSearchZoom applies orientation-dependent minimum and maximum', () => {
	assert.equal(clampSearchZoom(10), 10);
	assert.equal(clampSearchZoom(2), SEARCH_FIT_MIN_ZOOM_LANDSCAPE);
	assert.equal(
		clampSearchZoom(2, { portrait: true }),
		SEARCH_FIT_MIN_ZOOM_PORTRAIT,
	);
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

test('clampSearchZoom respects an optional radius-based maximum', () => {
	assert.equal(clampSearchZoom(18, { maxZoom: 10 }), 10);
	assert.equal(clampSearchZoom(2, { maxZoom: 10 }), SEARCH_FIT_MIN_ZOOM_LANDSCAPE);
	assert.equal(
		clampSearchZoom(18, { portrait: true, maxZoom: 20 }),
		SEARCH_FIT_MAX_ZOOM_PORTRAIT,
	);
	assert.equal(clampSearchZoom(18, { maxZoom: 2 }), SEARCH_FIT_MIN_ZOOM_LANDSCAPE);
});

test('zoomForRadius fits a radius into the viewport', () => {
	assert.equal(zoomForRadius(8300, 0, 900), 12);
	assert.equal(zoomForRadius(8300, 50, 390), 10);
	assert.equal(zoomForRadius(2500, 50, 390), 12);
	assert.equal(zoomForRadius(Number.NaN, 50, 390), null);
	assert.equal(zoomForRadius(0, 50, 390), null);
	assert.equal(zoomForRadius(8300, 50, 80), null);
});

test('radiusZoomLimit fits roughly three quarters of the circles', () => {
	const results = [
		{ lat: 0, radius: 2000 },
		{ lat: 0, radius: 4000 },
		{ lat: 0, radius: 6000 },
		{ lat: 0, radius: 8000 },
	];

	assert.equal(radiusZoomLimit(results, { viewportMinDimension: 900 }), 13);
	assert.equal(radiusZoomLimit([...results, { lat: 0, radius: 200000 }], {
		viewportMinDimension: 900,
	}), 12);
	assert.equal(radiusZoomLimit([], { viewportMinDimension: 900 }), null);
	assert.equal(radiusZoomLimit(results, { viewportMinDimension: Number.NaN }), null);
});

test('isPointInView and countPointsInView use the available viewport', () => {
	const center = { x: 0, y: 0 };

	assert.equal(isPointInView({ x: 100, y: 50 }, center, 200, 100), true);
	assert.equal(isPointInView({ x: 101, y: 0 }, center, 200, 100), false);
	assert.equal(isPointInView(null, center, 200, 100), false);
	assert.equal(countPointsInView([
		{ x: 0, y: 0 },
		{ x: 100, y: 50 },
		{ x: 300, y: 0 },
	], center, 200, 100), 2);
});

test('findClosestFittingCenter keeps the preferred center when all points fit', () => {
	assert.deepEqual(
		findClosestFittingCenter(
			[{ x: 0, y: 0 }, { x: 100, y: 50 }],
			{ x: 50, y: 25 },
			200,
			100,
		),
		{ x: 50, y: 25 },
	);
});

test('findClosestFittingCenter moves the center only as far as needed', () => {
	assert.deepEqual(
		findClosestFittingCenter(
			[{ x: 0, y: 0 }, { x: 100, y: 50 }],
			{ x: 200, y: 200 },
			200,
			100,
		),
		{ x: 100, y: 50 },
	);
});

test('findClosestFittingCenter returns null when the points cannot fit', () => {
	assert.equal(
		findClosestFittingCenter(
			[{ x: 0, y: 0 }, { x: 300, y: 50 }],
			{ x: 150, y: 25 },
			200,
			100,
		),
		null,
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
