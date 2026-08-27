'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { buildStructuredQuery, parseAnalysisResponse, validateAnalysis } = require('../api/contract');

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
    title: null
}];
const nullableSnapshot = structuredClone(nullableUpstream);
const normalizedNullable = parseAnalysisResponse(nullableUpstream);
assert.equal(Object.hasOwn(normalizedNullable.features[0].matches[0], 'source_url'), false);
assert.equal(Object.hasOwn(normalizedNullable.features[0].matches[0].evidence[0], 'location'), false);
assert.deepEqual(normalizedNullable.features[1].matches, []);
assert.deepEqual(nullableUpstream, nullableSnapshot);

for (const invalidReferenceId of [1, null, '', {}, [], true]) {
    const invalidReferenceUpstream = structuredClone(valid);
    const match = invalidReferenceUpstream.features[0].matches[0];
    match.reference_id = invalidReferenceId;
    const snapshot = structuredClone(invalidReferenceUpstream);
    const normalized = parseAnalysisResponse(invalidReferenceUpstream);
    assert.equal(normalized.features[0].matches[0].reference_id, match.patent_id);
    assert.deepEqual(invalidReferenceUpstream, snapshot);
}

const missingReferenceUpstream = structuredClone(valid);
delete missingReferenceUpstream.features[0].matches[0].reference_id;
const normalizedMissingReference = parseAnalysisResponse(missingReferenceUpstream);
assert.equal(
    normalizedMissingReference.features[0].matches[0].reference_id,
    normalizedMissingReference.features[0].matches[0].patent_id
);

const numericReferenceUpstream = structuredClone(valid);
numericReferenceUpstream.features[0].matches[0].reference_id = 1;
numericReferenceUpstream.features[1].matches = [{
    ...structuredClone(numericReferenceUpstream.features[0].matches[0]),
    reference_id: 2
}];
numericReferenceUpstream.overall_assessment.status = 'novelty_not_found';
const normalizedNumericReferences = parseAnalysisResponse(numericReferenceUpstream);
assert.deepEqual(
    normalizedNumericReferences.features.map((feature) => feature.matches[0].reference_id),
    ['US20250376069A1', 'US20250376069A1']
);

const invalidNumericReference = structuredClone(valid);
invalidNumericReference.features[0].matches[0].reference_id = 1;
assert.throws(() => validateAnalysis(invalidNumericReference), /reference_id must be non-empty text/);

const invalidNumericPatent = structuredClone(valid);
invalidNumericPatent.features[0].matches[0].reference_id = 1;
invalidNumericPatent.features[0].matches[0].patent_id = 2;
assert.throws(() => parseAnalysisResponse(invalidNumericPatent), /must be non-empty text/);

const duplicateNumericReferences = structuredClone(valid);
duplicateNumericReferences.features[0].matches[0].reference_id = 1;
duplicateNumericReferences.features[0].matches.push({
    ...structuredClone(duplicateNumericReferences.features[0].matches[0]),
    reference_id: 2
});
assert.throws(() => parseAnalysisResponse(duplicateNumericReferences), /duplicate reference_id/);

const prompt = buildStructuredQuery('A controller and two contacts');
assert.match(prompt, /reference_id must be a non-empty JSON string, never a number/);
assert.match(prompt, /reuse exactly the same reference_id/);
assert.match(prompt, /Put the assessment enum only in overall_assessment\.status/);
assert.match(prompt, /Write the summary as evidence-first explanatory prose/);
assert.match(prompt, /never include a raw or Markdown-escaped assessment identifier/);
assert.match(prompt, /Start immediately with a retrieved-reference fact/);
assert.match(prompt, /Do not begin the summary with "The assessment", "The result", "Novelty", or "Inconclusive"/);
assert.match(prompt, /limited to the retrieved references rather than a legal conclusion/);

for (const invalidAssessmentStatus of [
    'Novelty indicated',
    'novelty indicated',
    String.raw`novelty\_indicated`,
    'NOVELTY_INDICATED',
    ' novelty_indicated '
]) {
    const invalid = structuredClone(valid);
    invalid.overall_assessment.status = invalidAssessmentStatus;
    assert.throws(() => validateAnalysis(invalid), /overall_assessment\.status is unsupported/);
}

const assessmentSummaryError = /overall_assessment\.summary must explain the evidence without repeating the assessment status/;
for (const invalidAssessmentSummary of [
    'The evidence comparison supports novelty_indicated for this disclosure.',
    'The evidence comparison supports NOVELTY_NOT_FOUND for this disclosure.',
    String.raw`The assessment is novelty\_indicated because no single reference discloses every feature.`,
    String.raw`The assessment is novelty\_not\_found because one reference discloses every feature.`,
    'Novelty is indicated because no single reference discloses every feature.',
    'Novelty indicated because no single reference discloses every feature.',
    'The assessment is novelty indicated because no single reference discloses every feature.',
    'Novelty was not found because one reference discloses every feature.',
    'Novelty not found because one reference discloses every feature.',
    'This result is inconclusive because the retrieved context is incomplete.',
    'Inconclusive because the retrieved context is incomplete.'
]) {
    const invalid = structuredClone(valid);
    invalid.overall_assessment.summary = invalidAssessmentSummary;
    assert.throws(() => validateAnalysis(invalid), assessmentSummaryError);
}

const escapedAssessmentSummary = structuredClone(valid);
escapedAssessmentSummary.overall_assessment.summary = String.raw`The assessment is novelty\_indicated because no single reference discloses every feature.`;
assert.throws(
    () => parseAnalysisResponse({ answer: JSON.stringify(escapedAssessmentSummary) }),
    assessmentSummaryError
);

const reasonOnlyInconclusive = structuredClone(valid);
reasonOnlyInconclusive.overall_assessment.status = 'inconclusive';
reasonOnlyInconclusive.overall_assessment.summary = 'The retrieved context does not address every material feature. This assessment is limited to the retrieved references and is not a legal conclusion.';
assert.deepEqual(validateAnalysis(reasonOnlyInconclusive), reasonOnlyInconclusive);

for (const invalidFeatureId of ['F1', 0, 1.5, true]) {
    const invalid = structuredClone(valid);
    invalid.features[0].feature_id = invalidFeatureId;
    assert.throws(() => validateAnalysis(invalid), /positive integer/);
}
assert.throws(() => validateAnalysis(load('analysis-v2.invalid-enum.json')), /unsupported/);
assert.throws(() => validateAnalysis(load('analysis-v2.invalid-duplicate.json')), /duplicate feature_id/);
const anticipating = structuredClone(valid);
anticipating.features[1].matches = [structuredClone(anticipating.features[0].matches[0])];
assert.throws(() => validateAnalysis(anticipating), /novelty_indicated conflicts/);
anticipating.overall_assessment.status = 'novelty_not_found';
assert.deepEqual(validateAnalysis(anticipating), anticipating);
anticipating.features[1].matches[0].status = 'partially_disclosed';
assert.throws(() => validateAnalysis(anticipating), /novelty_not_found requires/);
assert.throws(() => parseAnalysisResponse({ answer: 'legacy narrative' }), /not valid Schema v2 JSON/);
console.log('JavaScript contract fixtures passed');
