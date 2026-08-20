const hashtagConfig = require('../backend/hashtag_config.json');
const hashtagBaseUrl = (process.env.HASHTAG_BASE_URL || 'https://kg-api.hashtag.ai').replace(/\/$/, '');
const hashtagNamespace = (process.env.HASHTAG_NAMESPACE || hashtagConfig.namespace).trim();
const corpusName = (process.env.HASHTAG_CORPUS_NAME || hashtagConfig.corpus_name).trim();
if (!hashtagNamespace) throw new Error('Hashtag namespace must not be empty');
if (!corpusName) throw new Error('Hashtag corpus name must not be empty');
const baseUrl = `${hashtagBaseUrl}/${encodeURIComponent(hashtagNamespace)}/${encodeURIComponent(corpusName)}`;
const { ContractError, buildStructuredQuery, parseAnalysisResponse } = require('./contract');

function buildQuery(userText) {
    return buildStructuredQuery(userText);
}

function processQueryResponse(responseData) {
    return parseAnalysisResponse(responseData);
}

function invalidReportPayload(validationError, upstreamResponse) {
    const payload = { error: `Backend returned an invalid report: ${validationError}` };
    if (process.env.DEBUG_INVALID_REPORTS === 'true') {
        payload.debug = {
            validation_error: validationError,
            upstream_response: upstreamResponse
        };
    }
    return payload;
}

module.exports = async function handler(req, res) {
    res.setHeader('Cache-Control', 'no-store');

    if (req.method !== 'POST') {
        res.setHeader('Allow', 'POST');
        res.status(405).json({ error: 'Method not allowed' });
        return;
    }

    const apiKey = process.env.HASHTAG_API_KEY;
    if (!apiKey) {
        res.status(500).json({ error: 'HASHTAG_API_KEY not found in environment variables' });
        return;
    }

    if (!req.body || typeof req.body.text !== 'string' || !req.body.text.trim()) {
        res.status(400).json({ error: "Missing 'text' field in request body" });
        return;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);

    try {
        const query = buildQuery(req.body.text);
        const response = await fetch(`${baseUrl}/query`, {
            method: 'POST',
            headers: {
                'x-api-key': apiKey,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question: query }),
            signal: controller.signal
        });

        const responseText = await response.text();
        if (!response.ok) {
            res.status(response.status).json({
                error: `Backend API returned status ${response.status}`,
                detail: responseText
            });
            return;
        }

        let responseData;
        try {
            responseData = JSON.parse(responseText);
        } catch {
            res.status(502).json(invalidReportPayload('response was not valid JSON', responseText));
            return;
        }

        try {
            res.status(200).json(processQueryResponse(responseData));
        } catch (error) {
            if (error instanceof ContractError) {
                res.status(502).json(invalidReportPayload(error.message, responseData));
                return;
            }
            throw error;
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            res.status(504).json({ error: 'Request to backend API timed out' });
            return;
        }
        res.status(502).json({ error: `Could not connect to backend API: ${error.message}` });
    } finally {
        clearTimeout(timeout);
    }
};
