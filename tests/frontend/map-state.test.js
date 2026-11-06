import test from 'node:test';
import assert from 'node:assert/strict';

import {
	DEFAULT_MAP_VIEW,
	FILTER_PARAMS,
	LOCATION_TOLERANCE_DEGREES,
	filterSearchString,
	isSamePosition,
	parseMapState,
	resolveInitialMapState,
	shouldPersistMapState,
} from '../../docker/webserver/www_data/js/map-state.js';

test('FILTER_PARAMS lists the supported URL filter keys', () => {
	assert.deepEqual(FILTER_PARAMS, ['name', 'vm', 'lr', 'tr', 'other', 'tag']);
});

test('filterSearchString keeps only filter params in a stable order', () => {
	assert.equal(
		filterSearchString('?tag=vm&other=%23berlin&foo=1&vm=Flevo&vm=Quest'),
		'vm=Flevo&vm=Quest&other=%23berlin&tag=vm',
	);
	assert.equal(filterSearchString('?foo=1'), '');
	assert.equal(filterSearchString(''), '');
	assert.equal(filterSearchString(null), '');
});

test('parseMapState accepts valid state and normalizes search', () => {
	assert.deepEqual(
		parseMapState({ center: ['50.1', 11.2], zoom: '8', search: '?vm=Flevo&foo=1' }),
		{ center: [50.1, 11.2], zoom: 8, search: 'vm=Flevo' },
	);
	assert.deepEqual(
		parseMapState({ center: [50, 11], zoom: 7, search: null }),
		{ center: [50, 11], zoom: 7, search: '' },
	);
});

test('parseMapState rejects invalid state', () => {
	assert.equal(parseMapState(null), null);
	assert.equal(parseMapState([]), null);
	assert.equal(parseMapState({ center: [91, 11], zoom: 7, search: '' }), null);
	assert.equal(parseMapState({ center: [50, 181], zoom: 7, search: '' }), null);
	assert.equal(parseMapState({ center: [50, 11], zoom: 99, search: '' }), null);
	assert.equal(parseMapState({ center: [50, 11], zoom: 'nope', search: '' }), null);
	assert.equal(parseMapState({ center: [50, 11], zoom: 7, search: 42 }), null);
	assert.equal(parseMapState({ center: [null, null], zoom: 7, search: '' }), null);
	assert.equal(parseMapState({ center: ['', ''], zoom: 7, search: '' }), null);
	assert.equal(parseMapState({ center: [50, 11], zoom: null, search: '' }), null);
	assert.equal(parseMapState({ center: [50, 11], zoom: '', search: '' }), null);
});

test('isSamePosition compares coordinates within the location tolerance', () => {
	assert.equal(isSamePosition([52.5, 13.4], [52.5, 13.4]), true);
	assert.equal(isSamePosition([52.5, 13.4], [52.5 + LOCATION_TOLERANCE_DEGREES / 2, 13.4]), true);
	assert.equal(isSamePosition([52.5, 13.4], [52.6, 13.4]), false);
	assert.equal(isSamePosition(null, [52.5, 13.4]), false);
});

test('shouldPersistMapState blocks geolocation centers and suspended saves', () => {
	assert.equal(shouldPersistMapState({ center: [50, 11], lastLocation: null }), true);
	assert.equal(shouldPersistMapState({ center: [52.5, 13.4], lastLocation: [52.5, 13.4] }), false);
	assert.equal(shouldPersistMapState({ center: [52.5, 13.4], lastLocation: [52.5, 13.4], suspended: true }), false);
	assert.equal(shouldPersistMapState({ center: [50, 11], lastLocation: [52.5, 13.4] }), true);
});

test('resolveInitialMapState prefers URL filters over stored filters', () => {
	const result = resolveInitialMapState({
		urlSearch: '?vm=Flevo',
		stored: { center: [48, 9], zoom: 10, search: 'other=%23berlin' },
	});

	assert.deepEqual(result, {
		center: [48, 9],
		zoom: 10,
		search: 'vm=Flevo',
		applyStoredSearch: false,
	});
});

test('resolveInitialMapState restores stored filters when URL has none', () => {
	const result = resolveInitialMapState({
		urlSearch: '?foo=1',
		stored: { center: [48, 9], zoom: 10, search: 'other=%23berlin' },
	});

	assert.deepEqual(result, {
		center: [48, 9],
		zoom: 10,
		search: 'other=%23berlin',
		applyStoredSearch: true,
	});
});

test('resolveInitialMapState falls back to the default view', () => {
	assert.deepEqual(resolveInitialMapState({ urlSearch: '', stored: null }), {
		center: [...DEFAULT_MAP_VIEW.center],
		zoom: DEFAULT_MAP_VIEW.zoom,
		search: '',
		applyStoredSearch: false,
	});
});

test('resolveInitialMapState ignores invalid stored state', () => {
	assert.deepEqual(
		resolveInitialMapState({
			urlSearch: '',
			stored: { center: [999, 9], zoom: 10, search: 'vm=Flevo' },
		}),
		{
			center: [...DEFAULT_MAP_VIEW.center],
			zoom: DEFAULT_MAP_VIEW.zoom,
			search: '',
			applyStoredSearch: false,
		},
	);
});
