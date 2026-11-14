import test from 'node:test';
import assert from 'node:assert/strict';

import {
	MARKER_OFFSET_ARC_SPACING_PX,
	MARKER_OFFSET_MAX_METERS,
	MARKER_OFFSET_RING_STEP_PX,
	computeOffsetPixels,
	groupDuplicateMarkers,
	maxOffsetRadius,
	metersPerPixel,
	offsetLatLng,
	offsetScaleForZoom,
} from '../../docker/webserver/www_data/js/marker-offset.js';

test('groupDuplicateMarkers groups exact numeric coordinates', () => {
	const groups = groupDuplicateMarkers([
		{ lat: '50.0000000', lon: '11.0000000' },
		{ lat: 50, lon: 11 },
		{ lat: '50.0000001', lon: '11.0000000' },
		{ lat: '51', lon: '12' },
		{ lat: '51', lon: '12' },
	]);

	assert.equal(groups.length, 2);
	assert.deepEqual(groups[0].indexes, [0, 1]);
	assert.deepEqual(groups[1].indexes, [3, 4]);
});

test('groupDuplicateMarkers ignores invalid and incomplete coordinates', () => {
	const groups = groupDuplicateMarkers([
		{ lat: '50', lon: '11' },
		{ lat: '50', lon: '11' },
		{ lat: '', lon: '11' },
		{ lat: null, lon: null },
		{ lat: '95', lon: '11' },
		{ lat: '50', lon: '200' },
		{ lon: '11' },
		null,
	]);

	assert.equal(groups.length, 1);
	assert.deepEqual(groups[0].indexes, [0, 1]);
});

test('groupDuplicateMarkers requires two markers per group', () => {
	assert.deepEqual(
		groupDuplicateMarkers([{ lat: '50', lon: '11' }, { lat: '51', lon: '12' }]),
		[],
	);
	assert.deepEqual(groupDuplicateMarkers(null), []);
});

test('computeOffsetPixels handles empty and single groups', () => {
	assert.deepEqual(computeOffsetPixels(0), []);
	assert.deepEqual(computeOffsetPixels(1), [{ x: 0, y: 0 }]);
});

test('computeOffsetPixels places two markers opposite each other', () => {
	const offsets = computeOffsetPixels(2);

	assert.equal(offsets.length, 2);
	for (const offset of offsets)
		assert.ok(Math.abs(Math.hypot(offset.x, offset.y) - MARKER_OFFSET_RING_STEP_PX) < 1e-9);

	assert.ok(Math.abs(offsets[0].x + offsets[1].x) < 1e-9);
	assert.ok(Math.abs(offsets[0].y + offsets[1].y) < 1e-9);
});

test('computeOffsetPixels returns unique deterministic positions', () => {
	const first = computeOffsetPixels(52);
	const second = computeOffsetPixels(52);

	assert.deepEqual(first, second);
	assert.equal(first.length, 52);
	assert.equal(new Set(first.map(offset => `${offset.x.toFixed(6)}|${offset.y.toFixed(6)}`)).size, 52);
	assert.ok(maxOffsetRadius(first) <= MARKER_OFFSET_RING_STEP_PX * 4 + 1e-9);
});

test('computeOffsetPixels keeps the configured ring spacing', () => {
	const offsets = computeOffsetPixels(6, { ringStep: 20, arcSpacing: MARKER_OFFSET_ARC_SPACING_PX });

	assert.equal(offsets.length, 6);
	for (const offset of offsets)
		assert.ok(Math.abs(Math.hypot(offset.x, offset.y) - 20) < 1e-9);
});

test('metersPerPixel decreases with zoom', () => {
	const low = metersPerPixel(50, 7);
	const high = metersPerPixel(50, 18);

	assert.ok(low > high);
	assert.equal(metersPerPixel(Number.NaN, 10), null);
	assert.equal(metersPerPixel(50, Number.NaN), null);
});

test('offsetScaleForZoom keeps offsets small at low zoom and full at high zoom', () => {
	const low = offsetScaleForZoom({ latitude: 50, zoom: 7, maxRadiusPixels: 72 });
	const middle = offsetScaleForZoom({ latitude: 50, zoom: 15, maxRadiusPixels: 72 });
	const high = offsetScaleForZoom({ latitude: 50, zoom: 18, maxRadiusPixels: 72 });

	assert.ok(low >= 0 && low < 0.01);
	assert.ok(middle > low && middle < high);
	assert.equal(high, 1);
});

test('offsetScaleForZoom respects invalid and zero inputs', () => {
	assert.equal(offsetScaleForZoom({ latitude: 50, zoom: 10, maxRadiusPixels: 0 }), 0);
	assert.equal(offsetScaleForZoom({ latitude: 50, zoom: 10, maxRadiusPixels: 72, maxMeters: 0 }), 0);
	assert.equal(offsetScaleForZoom({ latitude: Number.NaN, zoom: 10, maxRadiusPixels: 72 }), 0);
	assert.equal(offsetScaleForZoom(), 0);
});

test('offsetLatLng returns the original point for zero offsets', () => {
	const result = offsetLatLng({ lat: 50, lon: 11, dx: 0, dy: 0, zoom: 18 });

	assert.ok(Math.abs(result[0] - 50) < 1e-9);
	assert.ok(Math.abs(result[1] - 11) < 1e-9);
});

test('offsetLatLng applies screen-axis offsets', () => {
	const north = offsetLatLng({ lat: 50, lon: 11, dx: 0, dy: -18, zoom: 18 });
	const east = offsetLatLng({ lat: 50, lon: 11, dx: 18, dy: 0, zoom: 18 });

	assert.ok(north[0] > 50);
	assert.ok(Math.abs(north[1] - 11) < 1e-9);
	assert.ok(east[1] > 11);
	assert.ok(Math.abs(east[0] - 50) < 1e-9);
});

test('offsetLatLng returns null for invalid inputs', () => {
	assert.equal(offsetLatLng({ lat: Number.NaN, lon: 11, zoom: 18 }), null);
	assert.equal(offsetLatLng({ lat: 50, lon: 11, zoom: Number.NaN }), null);
	assert.equal(offsetLatLng(), null);
});

test('maxOffsetRadius handles empty and invalid offsets', () => {
	assert.equal(maxOffsetRadius([]), 0);
	assert.equal(maxOffsetRadius(null), 0);
	assert.equal(maxOffsetRadius([{ x: 3, y: 4 }, { x: Number.NaN, y: 10 }]), 5);
});

test('default geographic cap is finite', () => {
	assert.ok(Number.isFinite(MARKER_OFFSET_MAX_METERS));
	assert.ok(MARKER_OFFSET_MAX_METERS > 0);
});
