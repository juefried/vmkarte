import test from 'node:test';
import assert from 'node:assert/strict';

import {
	GEOLOCATION_OPTIONS,
	describeGeolocationError,
} from '../../docker/webserver/www_data/js/location.js';

test('GEOLOCATION_OPTIONS requests one high-accuracy position', () => {
	assert.equal(GEOLOCATION_OPTIONS.enableHighAccuracy, true);
	assert.equal(GEOLOCATION_OPTIONS.timeout, 10000);
	assert.equal(GEOLOCATION_OPTIONS.maximumAge, 0);
});

test('describeGeolocationError explains permission denied', () => {
	assert.equal(
		describeGeolocationError({ code: 1 }),
		'Standortzugriff wurde verweigert. Bitte die Berechtigung im Browser erlauben.',
	);
});

test('describeGeolocationError explains unavailable position', () => {
	assert.equal(
		describeGeolocationError({ code: 2 }),
		'Der Standort ist derzeit nicht verfügbar. Bitte später erneut versuchen.',
	);
});

test('describeGeolocationError explains a timeout', () => {
	assert.equal(
		describeGeolocationError({ code: 3 }),
		'Die Standortabfrage hat zu lange gedauert. Bitte erneut versuchen.',
	);
});

test('describeGeolocationError hides unknown technical errors', () => {
	assert.equal(
		describeGeolocationError({ code: 99, message: 'kCLErrorDomain' }),
		'Der Standort konnte nicht ermittelt werden.',
	);
	assert.equal(
		describeGeolocationError(null),
		'Der Standort konnte nicht ermittelt werden.',
	);
});
