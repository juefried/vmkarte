import test from 'node:test';
import assert from 'node:assert/strict';

import { collectSearchSuggestions } from '../../docker/webserver/www_data/js/search-suggestions.js';

test('collects names, vehicle labels and hashtags', () => {
	const suggestions = collectSearchSuggestions([
		{ name: 'Alpha', vm: 'DF XL', lr: 'Flux V-220', tr: 'KMX Venom', other: 'Tour #berlin' },
		{ name: 'Beta', vm: 'Quest', lr: '', tr: '', other: '#berlin #Übernachtung' },
	]);

	assert.ok(suggestions.includes('Alpha'));
	assert.ok(suggestions.includes('Beta'));
	assert.ok(suggestions.includes('DF XL'));
	assert.ok(suggestions.includes('Flux V-220'));
	assert.ok(suggestions.includes('KMX Venom'));
	assert.ok(suggestions.includes('#berlin'));
	assert.ok(suggestions.includes('#übernachtung'));
});

test('deduplicates case-insensitively and keeps the first spelling', () => {
	const suggestions = collectSearchSuggestions([
		{ name: 'Alpha', vm: 'DF XL' },
		{ name: 'alpha', vm: 'df xl' },
	]);

	assert.deepEqual(suggestions, ['Alpha', 'DF XL']);
});

test('sorts common values first, then alphabetically', () => {
	const suggestions = collectSearchSuggestions([
		{ name: 'Zeta', vm: 'Quest' },
		{ name: 'Alpha', vm: 'Quest' },
		{ name: 'Beta', vm: 'DF' },
	]);

	assert.deepEqual(suggestions, ['Quest', 'Alpha', 'Beta', 'DF', 'Zeta']);
});

test('ignores empty and non-string values', () => {
	const suggestions = collectSearchSuggestions([
		{ name: '', vm: null, lr: undefined, tr: 42, other: '' },
		{ name: 'Alpha', other: null },
		null,
	]);

	assert.deepEqual(suggestions, ['Alpha']);
});

test('handles missing members gracefully', () => {
	assert.deepEqual(collectSearchSuggestions(null), []);
	assert.deepEqual(collectSearchSuggestions([]), []);
});
