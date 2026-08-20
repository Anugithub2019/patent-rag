import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.dirname(__dirname);
const port = Number(process.env.PORT || 3000);
const require = createRequire(import.meta.url);

class UpstreamHttpError extends Error {}

class InvalidReportError extends Error {
    constructor(validationError, upstreamResponse) {
        super(`Backend returned an invalid report: ${validationError}`);
        this.name = 'InvalidReportError';
        this.validationError = validationError;
        this.upstreamResponse = upstreamResponse;
    }
}

// In-memory job store for async query support
const jobs = new Map();
const JOB_TTL = 3600_000; // 1 hour

loadDotEnv(path.join(rootDir, '.env'));
loadDotEnv(path.join(__dirname, '.env'));

const hashtagConfig = JSON.parse(
    readFileSync(path.join(rootDir, 'backend', 'hashtag_config.json'), 'utf8')
);
const hashtagBaseUrl = (process.env.HASHTAG_BASE_URL || 'https://kg-api.hashtag.ai').replace(/\/$/, '');
const hashtagNamespace = (process.env.HASHTAG_NAMESPACE || hashtagConfig.namespace).trim();
const corpusName = (process.env.HASHTAG_CORPUS_NAME || hashtagConfig.corpus_name).trim();
if (!hashtagNamespace) throw new Error('Hashtag namespace must not be empty');
if (!corpusName) throw new Error('Hashtag corpus name must not be empty');
const baseUrl = `${hashtagBaseUrl}/${encodeURIComponent(hashtagNamespace)}/${encodeURIComponent(corpusName)}`;
const { ContractError, buildStructuredQuery, parseAnalysisResponse } = require('../api/contract.js');

function loadDotEnv(filePath) {
    if (!existsSync(filePath)) {
        return;
    }

    const lines = readFileSync(filePath, 'utf8').split(/\r?\n/);
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) {
            continue;
        }

        const [key, ...valueParts] = trimmed.split('=');
        const value = valueParts.join('=').trim().replace(/^["']|["']$/g, '');
        if (!process.env[key.trim()]) {
            process.env[key.trim()] = value;
        }
    }
}

function sendJson(res, statusCode, data) {
    const body = JSON.stringify(data, null, 2);
    res.writeHead(statusCode, {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': Buffer.byteLength(body),
        'Cache-Control': 'no-store'
    });
    res.end(body);
}

function invalidReportDebug(error) {
    if (!(error instanceof InvalidReportError) || process.env.DEBUG_INVALID_REPORTS !== 'true') {
        return undefined;
    }

    return {
        validation_error: error.validationError,
        upstream_response: error.upstreamResponse
    };
}

async function sendFile(res, filePath, contentType) {
    const body = await readFile(filePath);
    res.writeHead(200, {
        'Content-Type': contentType,
        'Content-Length': body.length
    });
    res.end(body);
}

async function readJsonBody(req) {
    const chunks = [];
    for await (const chunk of req) {
        chunks.push(chunk);
    }
    const body = Buffer.concat(chunks).toString('utf8');
    return body ? JSON.parse(body) : {};
}

function buildQuery(userText) {
    return buildStructuredQuery(userText);
}

function processQueryResponse(responseData) {
    return parseAnalysisResponse(responseData);
}

async function fetchFromHashtag(documentText) {
    const apiKey = process.env.HASHTAG_API_KEY;
    if (!apiKey) {
        throw new Error('HASHTAG_API_KEY not found in environment variables');
    }

    const query = buildQuery(documentText);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);

    try {
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
            throw new UpstreamHttpError(`Backend API returned status ${response.status}: ${responseText}`);
        }

        let responseData;
        try {
            responseData = JSON.parse(responseText);
        } catch {
            throw new InvalidReportError('response was not valid JSON', responseText);
        }

        try {
            return processQueryResponse(responseData);
        } catch (error) {
            if (error instanceof ContractError) {
                throw new InvalidReportError(error.message, responseData);
            }
            throw error;
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new Error('Request to backend API timed out');
        }
        if (error instanceof InvalidReportError) {
            throw error;
        }
        if (error instanceof UpstreamHttpError) {
            throw error;
        }
        throw new Error(`Could not connect to backend API: ${error.message}`);
    } finally {
        clearTimeout(timeout);
    }
}

async function handleSubmitQuery(req, res) {
    let data;
    try {
        data = await readJsonBody(req);
    } catch {
        sendJson(res, 400, { error: 'Invalid JSON request body' });
        return;
    }

    if (!data || typeof data.text !== 'string' || !data.text.trim()) {
        sendJson(res, 400, { error: "Missing 'text' field in request body" });
        return;
    }

    const jobId = crypto.randomUUID();
    const job = { status: 'pending', createdAt: Date.now() };
    jobs.set(jobId, job);

    // Kick off the async query
    fetchFromHashtag(data.text)
        .then((parsed) => {
            job.status = 'complete';
            job.data = parsed;
        })
        .catch((error) => {
            job.status = 'failed';
            job.error = error.message;
            job.debug = invalidReportDebug(error);
        });

    // Clean up old jobs periodically
    setTimeout(() => jobs.delete(jobId), JOB_TTL);

    sendJson(res, 202, { job_id: jobId });
}

function handleGetResult(req, res, jobId) {
    const job = jobs.get(jobId);
    if (!job) {
        sendJson(res, 404, { error: 'Job not found' });
        return;
    }

    if (job.status === 'complete') {
        sendJson(res, 200, { status: 'complete', data: job.data });
    } else if (job.status === 'failed') {
        const result = { status: 'failed', error: job.error };
        if (job.debug) result.debug = job.debug;
        sendJson(res, 200, result);
    } else {
        sendJson(res, 200, { status: 'pending' });
    }
}

async function handleSearch(req, res) {
    let data;
    try {
        data = await readJsonBody(req);
    } catch {
        sendJson(res, 400, { error: 'Invalid JSON request body' });
        return;
    }

    if (!data || typeof data.text !== 'string' || !data.text.trim()) {
        sendJson(res, 400, { error: "Missing 'text' field in request body" });
        return;
    }

    try {
        const parsed = await fetchFromHashtag(data.text);
        sendJson(res, 200, parsed);
    } catch (error) {
        const result = { error: error.message };
        const debug = invalidReportDebug(error);
        if (debug) result.debug = debug;
        sendJson(res, 502, result);
    }
}

const server = createServer(async (req, res) => {
    try {
        const url = new URL(req.url, `http://${req.headers.host}`);

        // Serve frontend HTML
        if (req.method === 'GET' && url.pathname === '/') {
            await sendFile(res, path.join(__dirname, '..', 'frontend', 'search.html'), 'text/html; charset=utf-8');
            return;
        }

        // Serve report page
        if (req.method === 'GET' && url.pathname === '/report.html') {
            await sendFile(res, path.join(__dirname, '..', 'frontend', 'report.html'), 'text/html; charset=utf-8');
            return;
        }

        // Serve shared frontend styles
        if (req.method === 'GET' && url.pathname === '/styles.css') {
            await sendFile(res, path.join(__dirname, '..', 'frontend', 'styles.css'), 'text/css; charset=utf-8');
            return;
        }

        // Health check
        if (req.method === 'GET' && url.pathname === '/api/health') {
            sendJson(res, 200, { status: 'ok' });
            return;
        }

        // Legacy synchronous search
        if (req.method === 'POST' && url.pathname === '/api/search') {
            await handleSearch(req, res);
            return;
        }

        // Async query submission (frontend uses this)
        if (req.method === 'POST' && url.pathname === '/api/query') {
            await handleSubmitQuery(req, res);
            return;
        }

        // Poll for job result (frontend uses this)
        const resultMatch = url.pathname.match(/^\/api\/result\/([a-f0-9-]+)$/i);
        if (req.method === 'GET' && resultMatch) {
            handleGetResult(req, res, resultMatch[1]);
            return;
        }

        sendJson(res, 404, { error: 'Not found' });
    } catch (error) {
        sendJson(res, 500, { error: `Internal server error: ${error.message}` });
    }
});

server.listen(port, '0.0.0.0', () => {
    console.log(`PatentRAG frontend server running at http://localhost:${port}`);
});
