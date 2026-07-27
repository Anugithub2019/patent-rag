import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.dirname(__dirname);
const port = Number(process.env.PORT || 3000);
const baseUrl = 'https://kg-api.hashtag.ai/patentrag';

// In-memory job store for async query support
const jobs = new Map();
const JOB_TTL = 3600_000; // 1 hour

loadDotEnv(path.join(rootDir, '.env'));
loadDotEnv(path.join(__dirname, '.env'));

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
        'Content-Length': Buffer.byteLength(body)
    });
    res.end(body);
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

const QUESTION_PREFIXES = [
    "is there", "what", "find", "summarize",
    "does", "can", "how", "why", "which", "who",
    "list", "tell", "show", "give", "identify",
    "describe", "explain", "compare", "evaluate",
    "search", "retrieve", "do", "are", "will"
];

function buildQuery(userText) {
    const text = String(userText).trim();
    if (!text) return "";

    const firstWord = text.split(/\s+/)[0].toLowerCase().replace(/[?,.;:!]+$/, "");
    if (QUESTION_PREFIXES.includes(firstWord)) {
        return text;
    }

    return `Is there any novelty in this technology? Technology draft: ${text}`;
}

function extractChunkDetails(responseData) {
    const chunkDetails = responseData?.info?.nodedetails?.chunkdetails;
    return Array.isArray(chunkDetails) ? chunkDetails : [];
}

function extractSources(responseData) {
    const sources = responseData?.info?.sources;
    return Array.isArray(sources) ? sources : [];
}

function buildPatentTitle(chunkId, maxChars = 12) {
    const truncated = chunkId ? String(chunkId).slice(0, maxChars) : 'unknown';
    return `Patent Document (chunk: ${truncated}...)`;
}

function processQueryResponse(responseData) {
    const results = extractChunkDetails(responseData)
        .map((chunk) => {
            const chunkId = chunk.id || 'unknown';
            return {
                patent_id: chunkId,
                title: buildPatentTitle(chunkId),
                similarity: Number(chunk.score || 0),
                snippet: chunk.text || ''
            };
        })
        .sort((a, b) => b.similarity - a.similarity);

    const contexts = responseData?.info?.metric_details?.contexts || '';
    return {
        results,
        answer: responseData?.answer || '',
        sources: extractSources(responseData),
        contexts: String(contexts),
        total_results: results.length
    };
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
            throw new Error(`Backend API returned status ${response.status}: ${responseText}`);
        }

        return processQueryResponse(JSON.parse(responseText));
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new Error('Request to backend API timed out');
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

    if (!data || typeof data.text !== 'string') {
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
        sendJson(res, 200, { status: 'failed', error: job.error });
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

    if (!data || typeof data.text !== 'string') {
        sendJson(res, 400, { error: "Missing 'text' field in request body" });
        return;
    }

    try {
        const parsed = await fetchFromHashtag(data.text);
        sendJson(res, 200, parsed);
    } catch (error) {
        sendJson(res, 502, { error: error.message });
    }
}

const server = createServer(async (req, res) => {
    try {
        const url = new URL(req.url, `http://${req.headers.host}`);

        // Serve frontend HTML
        if (req.method === 'GET' && url.pathname === '/') {
            await sendFile(res, path.join(__dirname, '..', 'frontend', 'index.html'), 'text/html; charset=utf-8');
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