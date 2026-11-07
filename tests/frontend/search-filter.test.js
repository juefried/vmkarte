import test from 'node:test';
import assert from 'node:assert/strict';

import {
	SEARCH_MODE_EVERYWHERE_INDEX,
	SEARCH_MODE_HASHTAG_INDEX,
	filterMembers,
	resolveSearchMode,
} from '../../docker/webserver/www_data/js/search-filter.js';

const members = [
	{ id: '1', name: 'Alpha', vm: 'Flevo', lr: '', tr: '', other: 'Tour #berlin' },
	{ id: '2', name: 'Beta', vm: 'Quest', lr: 'Liegerad', tr: '', other: '#berlin #übernachtung' },
];

test('resolveSearchMode activates the search for any non-empty value', () => {
	assert.equal(resolveSearchMode('Alpha', 0), SEARCH_MODE_EVERYWHERE_INDEX);
	assert.equal(resolveSearchMode('A', 0), SEARCH_MODE_EVERYWHERE_INDEX);
	assert.equal(resolveSearchMode('Alpha', SEARCH_MODE_HASHTAG_INDEX), SEARCH_MODE_EVERYWHERE_INDEX);
	assert.equal(resolveSearchMode('#berlin', 0), SEARCH_MODE_HASHTAG_INDEX);
	assert.equal(resolveSearchMode('#berlin', SEARCH_MODE_EVERYWHERE_INDEX), SEARCH_MODE_HASHTAG_INDEX);
});

test('resolveSearchMode keeps the current mode for empty or invalid values', () => {
	assert.equal(resolveSearchMode('', 0), 0);
	assert.equal(resolveSearchMode('', SEARCH_MODE_EVERYWHERE_INDEX), SEARCH_MODE_EVERYWHERE_INDEX);
	assert.equal(resolveSearchMode(null, 2), 2);
	assert.equal(resolveSearchMode(undefined, 2), 2);
});

test('filterMembers ignores the query when the search bit is not set', () => {
	assert.deepEqual(filterMembers(members, { mode: 1, query: 'nicht-vorhanden' }), members);
});

test('filterMembers returns no members for a query without matches', () => {
	assert.deepEqual(filterMembers(members, { mode: 63, query: 'nicht-vorhanden' }), []);
});

test('filterMembers searches all matching fields', () => {
	assert.deepEqual(filterMembers(members, { mode: 63, query: 'alpha' }), [members[0]]);
	assert.deepEqual(filterMembers(members, { mode: 63, query: 'quest' }), [members[1]]);
	assert.deepEqual(filterMembers(members, { mode: 63, query: 'liegerad' }), [members[1]]);
	assert.deepEqual(filterMembers(members, { mode: 63, query: '#berlin' }), members);
});

test('filterMembers respects the selected search fields', () => {
	assert.deepEqual(filterMembers(members, { mode: 33, query: 'beta' }), [members[1]]);
	assert.deepEqual(filterMembers(members, { mode: 33, query: 'flevo' }), []);
	assert.deepEqual(filterMembers(members, { mode: 48, query: '#berlin' }), members);
	assert.deepEqual(filterMembers(members, { mode: 48, query: 'flevo' }), []);
});

test('filterMembers combines URL filters and form search', () => {
	const urlParams = new URLSearchParams('vm=Quest');
	assert.deepEqual(filterMembers(members, { urlParams, mode: 63, query: 'beta' }), [members[1]]);
	assert.deepEqual(filterMembers(members, { urlParams, mode: 63, query: 'alpha' }), []);
});

test('filterMembers filters by URL parameters alone', () => {
	assert.deepEqual(
		filterMembers(members, { urlParams: new URLSearchParams('name=Alpha'), mode: 1 }),
		[members[0]],
	);
	assert.deepEqual(
		filterMembers(members, { urlParams: new URLSearchParams('other=berlin'), mode: 1 }),
		members,
	);
	assert.deepEqual(
		filterMembers(members, { urlParams: new URLSearchParams('lr=liegerad'), mode: 1 }),
		[members[1]],
	);
	assert.deepEqual(
		filterMembers(members, { urlParams: new URLSearchParams('name=Gamma'), mode: 1 }),
		[],
	);
});

test('filterMembers handles invalid member input', () => {
	assert.deepEqual(filterMembers(null, { mode: 63, query: 'alpha' }), []);
	assert.deepEqual(filterMembers(undefined, { mode: 1 }), []);
});
