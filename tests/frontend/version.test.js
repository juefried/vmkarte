import test from 'node:test';
import assert from 'node:assert/strict';

import {
	DEV_MODE_KEY,
	parseAppVersion,
	isNewVersion,
	resolveDevMode,
} from '../../docker/webserver/www_data/js/version-check.js';

test('parseAppVersion accepts version and build date', () => {
	assert.deepEqual(
		parseAppVersion({ version: ' 3.0.0 ', buildDate: ' 2026-11-06T10:00:00Z ' }),
		{ version: '3.0.0', buildDate: '2026-11-06T10:00:00Z' },
	);
});

test('parseAppVersion rejects missing or invalid version', () => {
	assert.equal(parseAppVersion(null), null);
	assert.equal(parseAppVersion({}), null);
	assert.equal(parseAppVersion({ version: '' }), null);
	assert.equal(parseAppVersion({ version: 3 }), null);
});

test('parseAppVersion treats missing build date as null', () => {
	assert.deepEqual(parseAppVersion({ version: '3.0.0' }), { version: '3.0.0', buildDate: null });
});

test('isNewVersion uses exact inequality', () => {
	assert.equal(isNewVersion('3.0.0', '3.0.0'), false);
	assert.equal(isNewVersion('3.0.0 ', ' 3.0.0'), false);
	assert.equal(isNewVersion('3.0.0', '3.0.1'), true);
	assert.equal(isNewVersion('3.0.0', ''), false);
	assert.equal(isNewVersion(undefined, '3.0.1'), false);
});

test('resolveDevMode enables and persists with dev=1', () => {
	assert.deepEqual(resolveDevMode('?dev=1', null), { enabled: true, persist: true, clear: false });
});

test('resolveDevMode disables and clears with dev=0', () => {
	assert.deepEqual(resolveDevMode('?dev=0', '1'), { enabled: false, persist: false, clear: true });
});

test('resolveDevMode restores a stored tab session', () => {
	assert.deepEqual(resolveDevMode('', '1'), { enabled: true, persist: false, clear: false });
	assert.deepEqual(resolveDevMode('', null), { enabled: false, persist: false, clear: false });
});

test('resolveDevMode ignores non-boolean dev values', () => {
	assert.deepEqual(resolveDevMode('?dev=true', null), { enabled: false, persist: false, clear: false });
});

test('DEV_MODE_KEY is stable', () => {
	assert.equal(DEV_MODE_KEY, 'vmkarte-dev-mode');
});
