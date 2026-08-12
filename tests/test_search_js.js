'use strict';

const assert = require('node:assert/strict');
const handler = require('../api/search');

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
        global.fetch = async () => ({
            ok: true,
            text: async () => JSON.stringify({
                schema_version: 2,
                overall_assessment: { status: 'inconclusive', summary: 'Insufficient context.' },
                features: [{ feature_id: 0, feature_text: 'A feature', matches: [] }]
            })
        });

        const res = mockResponse();
        await handler({ method: 'POST', body: { text: 'A technology disclosure' } }, res);

        assert.equal(res.statusCode, 502);
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
