import test from 'node:test';
import assert from 'node:assert/strict';

import {
	parseDataStatus,
	validateMembers,
	isServerNewer,
	formatStatusTimestamp,
	isStale,
	deriveStatusFromLastModified,
	formatStatusText,
} from '../../docker/webserver/www_data/js/data.js';

test('parseDataStatus accepts valid status', () => {
	assert.deepEqual(
		parseDataStatus({ generatedAt: '2026-11-06T03:33:00+01:00', memberCount: 3167 }),
		{ generatedAt: '2026-11-06T03:33:00+01:00', runStartedAt: null, memberCount: 3167 },
	);
});

test('parseDataStatus accepts and keeps runStartedAt', () => {
	assert.deepEqual(
		parseDataStatus({
			runStartedAt: '2026-11-06T03:25:00+01:00',
			generatedAt: '2026-11-06T03:33:00+01:00',
			memberCount: 3167,
		}),
		{
			generatedAt: '2026-11-06T03:33:00+01:00',
			runStartedAt: '2026-11-06T03:25:00+01:00',
			memberCount: 3167,
		},
	);
});

test('parseDataStatus rejects invalid timestamp and member count', () => {
	assert.equal(parseDataStatus({ generatedAt: 'nope', memberCount: 1 }), null);
	assert.equal(parseDataStatus({ generatedAt: '2026-11-06T03:33:00+01:00', memberCount: -1 }), null);
	assert.equal(parseDataStatus({ generatedAt: '2026-11-06T03:33:00+01:00', memberCount: 1.5 }), null);
	assert.equal(parseDataStatus({ generatedAt: '2026-11-06T03:33:00+01:00', memberCount: 1, runStartedAt: 'nope' }), null);
	assert.equal(parseDataStatus(null), null);
});

test('validateMembers skips invalid entries', () => {
	const result = validateMembers([
		{ id: '1', name: 'A', lat: '50.0', lon: '10.0' },
		{ id: '2', name: 'B', lat: 'nope', lon: '10.0' },
		{ id: '3', name: '', lat: '50.0', lon: '10.0' },
		{ id: '4', name: 'D', lat: null, lon: '10.0' },
	]);

	assert.equal(result.members.length, 1);
	assert.equal(result.skipped, 3);
});

test('validateMembers rejects non-arrays and empty result', () => {
	assert.equal(validateMembers({}), null);
	assert.equal(validateMembers([{ id: '1' }]), null);
});

test('isServerNewer compares timestamps and handles missing local status', () => {
	assert.equal(isServerNewer({ generatedAt: '2026-11-06T04:00:00Z' }, null), true);
	assert.equal(isServerNewer({ generatedAt: '2026-11-06T04:00:00Z' }, { generatedAt: '2026-11-06T03:00:00Z' }), true);
	assert.equal(isServerNewer({ generatedAt: '2026-11-06T03:00:00Z' }, { generatedAt: '2026-11-06T03:00:00Z' }), false);
	assert.equal(isServerNewer({ generatedAt: '2026-11-06T02:00:00Z' }, { generatedAt: '2026-11-06T03:00:00Z' }), false);
});

test('formatStatusTimestamp formats German local time', () => {
	assert.match(
		formatStatusTimestamp('2026-11-06T03:33:00+01:00'),
		/^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}$/,
	);
	assert.equal(formatStatusTimestamp('nope'), 'unbekannt');
});

test('isStale uses the 48 hour threshold', () => {
	const now = Date.parse('2026-11-08T03:33:00Z');
	assert.equal(isStale('2026-11-06T03:33:00Z', now), false);
	assert.equal(isStale('2026-11-06T03:32:59Z', now), true);
	assert.equal(isStale(null, now), false);
});

test('deriveStatusFromLastModified parses HTTP dates', () => {
	const status = deriveStatusFromLastModified('Fri, 06 Nov 2026 02:33:00 GMT', 7);
	assert.equal(status.generatedAt, '2026-11-06T02:33:00.000Z');
	assert.equal(status.memberCount, 7);
	assert.equal(deriveStatusFromLastModified('nope', 7), null);
});

test('formatStatusText marks source and stale state', () => {
	assert.equal(
		formatStatusText({
			generatedAt: '2026-11-06T03:33:00+01:00',
			source: 'server',
			updateFailed: false,
			stale: false,
		}),
		'Datenstand: 06.11.2026, 03:33 · Server',
	);
	assert.match(
		formatStatusText({
			generatedAt: '2026-11-06T03:33:00+01:00',
			source: 'local',
			updateFailed: true,
			stale: true,
		}),
		/lokal \(Aktualisierung fehlgeschlagen\).*älter als 48 h/,
	);
	assert.equal(
		formatStatusText({ generatedAt: null, source: 'local', updateFailed: false, stale: false }),
		'Datenstand: unbekannt · lokal',
	);
	assert.equal(
		formatStatusText({
			generatedAt: '2026-11-06T03:33:00+01:00',
			source: 'server',
			updateFailed: true,
			stale: false,
		}),
		'Datenstand: 06.11.2026, 03:33 · Server (Aktualisierung fehlgeschlagen)',
	);
	assert.equal(
		formatStatusText({
			generatedAt: '2026-11-06T03:33:00+01:00',
			source: 'local',
			updateFailed: false,
			stale: false,
			offline: true,
		}),
		'Datenstand: 06.11.2026, 03:33 · lokal · offline',
	);
});
