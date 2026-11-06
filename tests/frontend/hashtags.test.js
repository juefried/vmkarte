import test from 'node:test';
import assert from 'node:assert/strict';

import {
	HASHTAG_REGEX,
	HASHTAG_NAME_REGEX,
} from '../../docker/webserver/www_data/js/hashtags.js';

function extractHashtags(text) {
	return text.match(HASHTAG_REGEX) ?? [];
}

test('extracts ASCII hashtags as before', () => {
	assert.deepEqual(
		extractHashtags('Treffen in #berlin mit #a1 und #foo_bar'),
		['#berlin', '#a1', '#foo_bar'],
	);
});

test('extracts German umlauts and ß', () => {
	assert.deepEqual(
		extractHashtags('#übernachtung #Übernachtung #straße'),
		['#übernachtung', '#Übernachtung', '#straße'],
	);
});

test('extracts accented and non-Latin letters', () => {
	assert.deepEqual(
		extractHashtags('#café #München #東京'),
		['#café', '#München', '#東京'],
	);
});

test('keeps the minimum length of two characters after #', () => {
	assert.deepEqual(extractHashtags('#a #ab #ü'), ['#ab']);
});

test('requires a letter directly after #', () => {
	assert.deepEqual(extractHashtags('# #1a #_x #123'), []);
});

test('replaces all hashtags in a text', () => {
	assert.equal(
		'Text #übernachtung, #café.'.replace(HASHTAG_REGEX, match => `[${match}]`),
		'Text [#übernachtung], [#café].',
	);
});

test('accepts Unicode tag names for the tag URL parameter', () => {
	assert.equal(HASHTAG_NAME_REGEX.test('übernachtung'), true);
	assert.equal(HASHTAG_NAME_REGEX.test('berlin'), true);
	assert.equal(HASHTAG_NAME_REGEX.test('123'), false);
	assert.equal(HASHTAG_NAME_REGEX.test('_x'), false);
});
