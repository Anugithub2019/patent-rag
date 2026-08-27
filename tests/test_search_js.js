'use strict';

const assert = require('node:assert/strict');
const handler = require('../api/search');
const validReport = require('./fixtures/analysis-v2.valid.json');

function mockResponse() {
    return {
        headers: {},
        statusCode: null,
        body: null,
        setHeader(name, value) { this.headers[name] = value; },
        status(code) { this.statusCode = code; return this; },
        json(body) { this.body = body; return this; }
    };
}

async function run() {
    const originalFetch = global.fetch;
    const originalApiKey = process.env.HASHTAG_API_KEY;
    const originalDebug = process.env.DEBUG_INVALID_REPORTS;
    process.env.HASHTAG_API_KEY = 'test-key';
    process.env.DEBUG_INVALID_REPORTS = 'true';

    try {
        let requestedUrl;
        global.fetch = async (url) => {
            requestedUrl = url;
            return ({
            ok: true,
            text: async () => JSON.stringify({
                schema_version: 2,
                overall_assessment: {
                    status: 'inconclusive',
                    summary: 'The retrieved context is insufficient to assess every material feature. This assessment is limited to the retrieved references and is not a legal conclusion.'
                },
                features: [{ feature_id: 0, feature_text: 'A feature', matches: [] }]
            })
            });
        };

        const res = mockResponse();
        await handler({ method: 'POST', body: { text: 'A technology disclosure' } }, res);

        assert.equal(res.statusCode, 502);
        assert.equal(requestedUrl, 'https://kg-api.hashtag.ai/rsongnov/patents_5530/query');
        assert.equal(res.headers['Cache-Control'], 'no-store');
        assert.match(res.body.error, /^Backend returned an invalid report:/);
        assert.doesNotMatch(res.body.error, /Could not connect/);
        assert.equal(res.body.debug.validation_error, 'features[0].feature_id must be a positive integer');
        assert.equal(res.body.debug.upstream_response.features[0].feature_id, 0);

        process.env.DEBUG_INVALID_REPORTS = 'false';
        const privateRes = mockResponse();
        await handler({ method: 'POST', body: { text: 'A technology disclosure' } }, privateRes);
        assert.equal(privateRes.statusCode, 502);
        assert.equal(privateRes.body.debug, undefined);

        process.env.DEBUG_INVALID_REPORTS = 'true';
        const escapedSummaryReport = structuredClone(validReport);
        escapedSummaryReport.overall_assessment.summary = String.raw`The assessment is novelty\_indicated because no single reference discloses every feature.`;
        const escapedSummaryUpstream = { answer: JSON.stringify(escapedSummaryReport) };
        global.fetch = async () => ({
            ok: true,
            text: async () => JSON.stringify(escapedSummaryUpstream)
        });

        const escapedSummaryRes = mockResponse();
        await handler({ method: 'POST', body: { text: 'A technology disclosure' } }, escapedSummaryRes);

        assert.equal(escapedSummaryRes.statusCode, 502);
        assert.match(
            escapedSummaryRes.body.error,
            /overall_assessment\.summary must explain the evidence without repeating the assessment status/
        );
        assert.deepEqual(escapedSummaryRes.body.debug.upstream_response, escapedSummaryUpstream);
    } finally {
        global.fetch = originalFetch;
        if (originalApiKey === undefined) delete process.env.HASHTAG_API_KEY;
        else process.env.HASHTAG_API_KEY = originalApiKey;
        if (originalDebug === undefined) delete process.env.DEBUG_INVALID_REPORTS;
        else process.env.DEBUG_INVALID_REPORTS = originalDebug;
    }

    console.log('JavaScript search error handling passed');
}

run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
