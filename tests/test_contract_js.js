'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { parseAnalysisResponse, validateAnalysis } = require('../api/contract');

const fixtures = path.join(__dirname, 'fixtures');
const load = (name) => JSON.parse(fs.readFileSync(path.join(fixtures, name), 'utf8'));

const valid = load('analysis-v2.valid.json');
assert.deepEqual(validateAnalysis(valid), valid);
assert.deepEqual(parseAnalysisResponse({ answer: JSON.stringify(valid) }), valid);

const nullableUpstream = structuredClone(valid);
nullableUpstream.features[0].matches[0].source_url = null;
nullableUpstream.features[0].matches[0].evidence[0].location = null;
nullableUpstream.features[1].matches = [{
    ...structuredClone(nullableUpstream.features[0].matches[0]),
    reference_id: null
}];
const nullableSnapshot = structuredClone(nullableUpstream);
const normalizedNullable = parseAnalysisResponse(nullableUpstream);
assert.equal(Object.hasOwn(normalizedNullable.features[0].matches[0], 'source_url'), false);
assert.equal(Object.hasOwn(normalizedNullable.features[0].matches[0].evidence[0], 'location'), false);
assert.deepEqual(normalizedNullable.features[1].matches, []);
assert.deepEqual(nullableUpstream, nullableSnapshot);

for (const invalidFeatureId of ['F1', 0, 1.5, true]) {
    const invalid = structuredClone(valid);
    invalid.features[0].feature_id = invalidFeatureId;
    assert.throws(() => validateAnalysis(invalid), /positive integer/);
}
assert.throws(() => validateAnalysis(load('analysis-v2.invalid-enum.json')), /unsupported/);
assert.throws(() => validateAnalysis(load('analysis-v2.invalid-duplicate.json')), /duplicate feature_id/);
assert.throws(() => parseAnalysisResponse({ answer: 'legacy narrative' }), /not valid Schema v2 JSON/);
console.log('JavaScript contract fixtures passed');
