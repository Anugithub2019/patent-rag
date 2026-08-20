'use strict';

const ASSESSMENTS = new Set(['novelty_indicated', 'novelty_not_found', 'inconclusive']);
const DISCLOSURES = new Set(['disclosed', 'partially_disclosed']);

class ContractError extends Error {}

function buildStructuredQuery(userText) {
    const text = String(userText).trim();
    return `Analyze the following technology disclosure against the retrieved patent context.
Return ONLY valid JSON (no Markdown) using schema_version 2 with: overall_assessment {status, summary}; and a non-empty features array whose items contain feature_id, feature_text, and matches. feature_id must be a unique positive JSON integer numbered 1, 2, 3, and so on (never a quoted string such as "F1"). Each match must contain non-empty reference_id, patent_id, title, status (disclosed or partially_disclosed), disclosure_summary, and an evidence array of {passage, optional location}; source_url is optional and must be http(s). Never output null. Omit optional location and source_url fields when unavailable. If any required match metadata is unavailable, omit that entire match and use an empty matches array when no complete match remains. Assessment status must be novelty_indicated, novelty_not_found, or inconclusive. Include every material feature and do not invent evidence or reference metadata. Use novelty_not_found only when one single reference has an evidence-supported disclosed (not partially_disclosed) match for every material feature. Use novelty_indicated only when the retrieved context is sufficient to assess every material feature and no single reference fully discloses all of them. Use inconclusive whenever the context or evidence is insufficient to apply either rule confidently. The summary must explain which rule was met, identify any single anticipation reference for novelty_not_found, and state that the result is limited to retrieved references rather than a legal conclusion.

Technology disclosure:
${text}`;
}

function record(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function unavailable(value) {
    return value === null || value === undefined || (typeof value === 'string' && !value.trim());
}

function normalizeAnalysisCandidate(candidate) {
    if (!record(candidate)) return candidate;

    // Upstream data is JSON. Clone it so debug output retains the exact raw response.
    const normalized = JSON.parse(JSON.stringify(candidate));
    if (!Array.isArray(normalized.features)) return normalized;

    const requiredMatchFields = [
        'reference_id',
        'patent_id',
        'title',
        'status',
        'disclosure_summary',
        'evidence'
    ];

    normalized.features.forEach((feature) => {
        if (!record(feature) || !Array.isArray(feature.matches)) return;

        feature.matches = feature.matches
            .filter((match) => {
                if (!record(match)) return true;
                return !requiredMatchFields.some(
                    (key) => !Object.prototype.hasOwnProperty.call(match, key) || unavailable(match[key])
                );
            })
            .map((match) => {
                if (!record(match)) return match;

                if (unavailable(match.source_url)) delete match.source_url;
                if (Array.isArray(match.evidence)) {
                    match.evidence = match.evidence
                        .filter((evidence) => !record(evidence) || !unavailable(evidence.passage))
                        .map((evidence) => {
                            if (record(evidence) && unavailable(evidence.location)) delete evidence.location;
                            return evidence;
                        });
                }
                return match;
            });
    });

    return normalized;
}

function text(value, path) {
    if (typeof value !== 'string' || !value.trim()) throw new ContractError(`${path} must be non-empty text`);
}

function positiveInteger(value, path) {
    if (!Number.isInteger(value) || value < 1) throw new ContractError(`${path} must be a positive integer`);
}

function exactKeys(value, allowed, path) {
    for (const key of Object.keys(value)) {
        if (!allowed.includes(key)) throw new ContractError(`${path}.${key} is not allowed`);
    }
}

function validateAnalysis(data) {
    if (!record(data) || data.schema_version !== 2) throw new ContractError('schema_version must be 2');
    exactKeys(data, ['schema_version', 'overall_assessment', 'features'], '$');
    const assessment = data.overall_assessment;
    if (!record(assessment)) throw new ContractError('overall_assessment must be an object');
    exactKeys(assessment, ['status', 'summary'], 'overall_assessment');
    if (!ASSESSMENTS.has(assessment.status)) throw new ContractError('overall_assessment.status is unsupported');
    text(assessment.summary, 'overall_assessment.summary');
    if (!Array.isArray(data.features) || !data.features.length) throw new ContractError('features must be a non-empty array');

    const featureIds = new Set();
    const metadata = new Map();
    data.features.forEach((feature, featureIndex) => {
        const path = `features[${featureIndex}]`;
        if (!record(feature)) throw new ContractError(`${path} must be an object`);
        exactKeys(feature, ['feature_id', 'feature_text', 'matches'], path);
        positiveInteger(feature.feature_id, `${path}.feature_id`);
        text(feature.feature_text, `${path}.feature_text`);
        if (featureIds.has(feature.feature_id)) throw new ContractError(`duplicate feature_id: ${feature.feature_id}`);
        featureIds.add(feature.feature_id);
        if (!Array.isArray(feature.matches)) throw new ContractError(`${path}.matches must be an array`);
        const referenceIds = new Set();
        feature.matches.forEach((match, matchIndex) => {
            const matchPath = `${path}.matches[${matchIndex}]`;
            if (!record(match)) throw new ContractError(`${matchPath} must be an object`);
            exactKeys(match, ['reference_id', 'patent_id', 'title', 'status', 'disclosure_summary', 'evidence', 'source_url'], matchPath);
            ['reference_id', 'patent_id', 'title', 'disclosure_summary'].forEach((key) => text(match[key], `${matchPath}.${key}`));
            if (!DISCLOSURES.has(match.status)) throw new ContractError(`${matchPath}.status is unsupported`);
            if (referenceIds.has(match.reference_id)) throw new ContractError(`duplicate reference_id ${match.reference_id} in feature ${feature.feature_id}`);
            referenceIds.add(match.reference_id);
            const currentMetadata = `${match.patent_id}\u0000${match.title}`;
            if (metadata.has(match.reference_id) && metadata.get(match.reference_id) !== currentMetadata) {
                throw new ContractError(`conflicting metadata for reference_id: ${match.reference_id}`);
            }
            metadata.set(match.reference_id, currentMetadata);
            if (!Array.isArray(match.evidence) || !match.evidence.length) throw new ContractError(`${matchPath}.evidence must be a non-empty array`);
            match.evidence.forEach((evidence, evidenceIndex) => {
                const evidencePath = `${matchPath}.evidence[${evidenceIndex}]`;
                if (!record(evidence)) throw new ContractError(`${evidencePath} must be an object`);
                exactKeys(evidence, ['passage', 'location'], evidencePath);
                text(evidence.passage, `${evidencePath}.passage`);
                if (evidence.location !== undefined) text(evidence.location, `${evidencePath}.location`);
            });
            if (match.source_url !== undefined) {
                text(match.source_url, `${matchPath}.source_url`);
                let url;
                try { url = new URL(match.source_url); } catch { throw new ContractError(`${matchPath}.source_url must be a URL`); }
                if (!['http:', 'https:'].includes(url.protocol)) throw new ContractError(`${matchPath}.source_url must use http(s)`);
            }
        });
    });
    const fullyDisclosedByFeature = data.features.map((feature) => new Set(
        feature.matches.filter((match) => match.status === 'disclosed').map((match) => match.reference_id)
    ));
    const anticipatingReferences = [...fullyDisclosedByFeature[0]].filter(
        (referenceId) => fullyDisclosedByFeature.every((referenceIds) => referenceIds.has(referenceId))
    );
    if (assessment.status === 'novelty_not_found' && !anticipatingReferences.length) {
        throw new ContractError('novelty_not_found requires one fully disclosing reference across every feature');
    }
    if (assessment.status === 'novelty_indicated' && anticipatingReferences.length) {
        throw new ContractError('novelty_indicated conflicts with a fully disclosing reference across every feature');
    }
    return data;
}

function parseAnalysisResponse(responseData) {
    if (!record(responseData)) throw new ContractError('upstream response must be an object');
    let candidate = responseData.schema_version === 2 ? responseData : responseData.answer;
    if (typeof candidate === 'string') {
        let value = candidate.trim();
        value = value.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
        try { candidate = JSON.parse(value); } catch { throw new ContractError('upstream answer is not valid Schema v2 JSON'); }
    }
    return validateAnalysis(normalizeAnalysisCandidate(candidate));
}

module.exports = { ContractError, buildStructuredQuery, parseAnalysisResponse, validateAnalysis };
