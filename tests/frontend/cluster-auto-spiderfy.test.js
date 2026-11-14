import test from 'node:test';
import assert from 'node:assert/strict';

import {
	AUTO_SPIDERFY_EDGE_MARGIN_PX,
	AUTO_SPIDERFY_MAX_PINS,
	shouldAutoSpiderfy,
} from '../../docker/webserver/www_data/js/cluster-auto-spiderfy.js';

function decision(overrides = {}) {
	return shouldAutoSpiderfy({
		visibleClusterCount: 1,
		childCount: 4,
		edgeDistancePixels: 200,
		...overrides,
	});
}

test('auto-spiderfy opens exactly one small cluster', () => {
	assert.equal(decision(), true);
	assert.equal(decision({ childCount: 2 }), true);
	assert.equal(decision({ childCount: AUTO_SPIDERFY_MAX_PINS }), true);
});

test('auto-spiderfy requires exactly one visible cluster', () => {
	assert.equal(decision({ visibleClusterCount: 0 }), false);
	assert.equal(decision({ visibleClusterCount: 2 }), false);
});

test('auto-spiderfy skips clusters with more than ten pins', () => {
	assert.equal(decision({ childCount: AUTO_SPIDERFY_MAX_PINS + 1 }), false);
	assert.equal(decision({ childCount: 50 }), false);
});

test('auto-spiderfy rejects invalid child counts', () => {
	assert.equal(decision({ childCount: 1 }), false);
	assert.equal(decision({ childCount: 0 }), false);
	assert.equal(decision({ childCount: 4.5 }), false);
	assert.equal(decision({ childCount: Number.NaN }), false);
});

test('auto-spiderfy keeps the spiral away from the viewport edge', () => {
	assert.equal(decision({ edgeDistancePixels: AUTO_SPIDERFY_EDGE_MARGIN_PX - 1 }), false);
	assert.equal(decision({ edgeDistancePixels: AUTO_SPIDERFY_EDGE_MARGIN_PX }), true);
	assert.equal(decision({ edgeDistancePixels: Number.POSITIVE_INFINITY }), false);
});

test('auto-spiderfy accepts explicit limits', () => {
	assert.equal(decision({ childCount: 12, maxPins: 12 }), true);
	assert.equal(decision({ edgeDistancePixels: 20, edgeMarginPixels: 20 }), true);
});
