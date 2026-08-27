'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const validReport = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'fixtures', 'analysis-v2.valid.json'), 'utf8')
);
const reportMarkup = fs.readFileSync(path.join(root, 'frontend', 'report.html'), 'utf8');
const reportStyles = fs.readFileSync(path.join(root, 'frontend', 'styles.css'), 'utf8');
const sessionReportKey = 'patentrag:report:analysis-v2';

class MemoryStorage {
    constructor(entries = {}) {
        this.entries = new Map(Object.entries(entries));
    }

    getItem(key) {
        return this.entries.has(key) ? this.entries.get(key) : null;
    }

    setItem(key, value) {
        this.entries.set(key, String(value));
    }

    removeItem(key) {
        this.entries.delete(key);
    }
}

function inlineApplicationScript(fileName) {
    const html = fs.readFileSync(path.join(root, 'frontend', fileName), 'utf8');
    const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
    const application = scripts.map((match) => match[1]).find((source) => source.includes('createApp({'));
    assert.ok(application, `${fileName} must contain an inline Vue application`);
    return application;
}

function ref(value) {
    return { value };
}

function computed(getter) {
    return {
        get value() {
            return getter();
        }
    };
}

function jsonResponse(status, body) {
    return {
        status,
        ok: status >= 200 && status < 300,
        json: async () => body
    };
}

function reportForAssessment(status, summary) {
    const report = JSON.parse(JSON.stringify(validReport));
    report.overall_assessment = { status, summary };

    if (status === 'novelty_not_found') {
        const anticipatingMatch = JSON.parse(JSON.stringify(report.features[0].matches[0]));
        anticipatingMatch.status = 'disclosed';
        report.features.forEach((feature) => {
            feature.matches = [JSON.parse(JSON.stringify(anticipatingMatch))];
        });
    }

    return report;
}

function mountStoredReport(report) {
    return mountReport({
        search: '?result_source=session-v2',
        storage: new MemoryStorage({ [sessionReportKey]: JSON.stringify(report) })
    });
}

function mountSearch(fetchImplementation, FileReaderImplementation) {
    let application;
    const storage = new MemoryStorage();
    const window = {
        location: { href: '' },
        sessionStorage: storage
    };
    const Vue = {
        ref,
        computed,
        nextTick: (callback) => Promise.resolve().then(callback),
        createApp(component) {
            return {
                mount() {
                    application = component.setup();
                }
            };
        }
    };

    vm.runInNewContext(inlineApplicationScript('search.html'), {
        Vue,
        window,
        FileReader: FileReaderImplementation,
        fetch: fetchImplementation,
        console: { error() {} }
    });

    return { application, storage, window };
}

function mountReport({ search, storage, fetchImplementation }) {
    let application;
    const mountedCallbacks = [];
    const intervalCallbacks = [];
    const window = {
        location: { search, hash: '', href: '' },
        sessionStorage: storage,
        matchMedia() {
            return {
                matches: false,
                addEventListener() {},
                removeEventListener() {}
            };
        }
    };
    const Vue = {
        ref,
        computed,
        onMounted(callback) {
            mountedCallbacks.push(callback);
        },
        onBeforeUnmount() {},
        createApp(component) {
            return {
                mount() {
                    application = component.setup();
                    mountedCallbacks.forEach((callback) => callback());
                }
            };
        }
    };

    vm.runInNewContext(inlineApplicationScript('report.html'), {
        Vue,
        window,
        URL,
        URLSearchParams,
        setInterval(callback) {
            intervalCallbacks.push(callback);
            return intervalCallbacks.length;
        },
        clearInterval() {},
        fetch: fetchImplementation || (async () => {
            throw new Error('The session-result path must not poll the job API');
        }),
        console: { error() {}, warn() {} }
    });

    return { application, intervalCallbacks, window };
}

async function run() {
    assert.match(reportMarkup, /<h3 id="assessmentResultTitle">Result<\/h3>/);
    assert.doesNotMatch(reportMarkup, /<h3[^>]*>Reason<\/h3>/);
    assert.match(reportMarkup, /<section class="assessment-part assessment-reason" aria-label="Assessment reason">/);
    assert.match(
        reportMarkup,
        /<p class="assessment-reason-text">\{\{ assessmentReason \}\}<\/p>/
    );
    assert.match(
        reportMarkup,
        /<strong>\{\{ assessmentResult \}\}<\/strong>/
    );
    assert.doesNotMatch(reportMarkup, /assessment-result-qualifier/);
    assert.doesNotMatch(reportMarkup, /v-html\s*=\s*["'][^"']*assessmentReason/);
    assert.match(
        reportStyles,
        /\.assessment-breakdown\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;/s
    );

    class SuccessfulFileReader {
        readAsText() {
            this.onload({ target: { result: 'Disclosure loaded from a text file' } });
        }
    }
    const upload = mountSearch(async () => {
        throw new Error('Uploading a local file must not call the search API');
    }, SuccessfulFileReader);
    upload.application.showStatus('Previous validation message', 'error');
    upload.application.onFileChange({
        target: { files: [{ name: 'disclosure.txt', type: 'text/plain' }] }
    });
    assert.equal(upload.application.documentText.value, 'Disclosure loaded from a text file');
    assert.equal(upload.application.fileName.value, 'disclosure.txt');
    assert.equal(upload.application.status.value.visible, false);
    assert.equal(upload.application.status.value.message, '');

    const localCalls = [];
    const local = mountSearch(async (url, options) => {
        localCalls.push({ url, options });
        return jsonResponse(202, { job_id: '11111111-1111-4111-8111-111111111111' });
    });
    local.application.documentText.value = 'A local asynchronous disclosure';
    await local.application.submitQuery();
    assert.deepEqual(localCalls.map(({ url }) => url), ['/api/query']);
    assert.equal(
        local.window.location.href,
        'report.html?job_id=11111111-1111-4111-8111-111111111111'
    );
    assert.equal(local.storage.getItem('patentrag:report:analysis-v2'), null);

    const fallbackCalls = [];
    const fallback = mountSearch(async (url, options) => {
        fallbackCalls.push({ url, options });
        if (url === '/api/query') return jsonResponse(404, { error: 'Not found' });
        return jsonResponse(200, validReport);
    });
    fallback.application.documentText.value = 'A Vercel synchronous disclosure';
    await fallback.application.submitQuery();
    assert.deepEqual(fallbackCalls.map(({ url }) => url), ['/api/query', '/api/search']);
    assert.deepEqual(
        fallbackCalls.map(({ options }) => JSON.parse(options.body)),
        [
            { text: 'A Vercel synchronous disclosure' },
            { text: 'A Vercel synchronous disclosure' }
        ]
    );
    assert.equal(fallback.window.location.href, 'report.html?result_source=session-v2');
    assert.deepEqual(
        JSON.parse(fallback.storage.getItem('patentrag:report:analysis-v2')),
        validReport
    );

    const completedReport = mountReport({
        search: '?result_source=session-v2',
        storage: fallback.storage
    });
    assert.equal(completedReport.application.reportState.value, 'complete');
    assert.equal(completedReport.application.normalizedFeatures.value.length, validReport.features.length);
    assert.equal(fallback.storage.getItem('patentrag:report:analysis-v2'), null);

    const assessmentCases = [
        {
            status: 'novelty_indicated',
            result: 'Novelty indicated',
            reason: 'No single retrieved reference discloses every material feature in the technical disclosure.'
        },
        {
            status: 'novelty_not_found',
            result: 'Novelty not found',
            reason: 'Reference R1 discloses every material feature in the technical disclosure.'
        },
        {
            status: 'inconclusive',
            result: 'Inconclusive',
            reason: 'The retrieved evidence is insufficient to assess every material feature.'
        }
    ];

    for (const assessmentCase of assessmentCases) {
        const assessmentReport = reportForAssessment(assessmentCase.status, assessmentCase.reason);
        const renderedAssessment = mountStoredReport(assessmentReport);

        assert.equal(renderedAssessment.application.reportState.value, 'complete');
        assert.equal(renderedAssessment.application.assessmentResult.value, assessmentCase.result);
        assert.equal(renderedAssessment.application.assessmentReason.value, assessmentCase.reason);
        assert.equal(renderedAssessment.application.overallAssessment.value.summary, assessmentCase.reason);
    }

    const escapedStatusReason = reportForAssessment(
        'novelty_indicated',
        'The assessment is novelty\\_indicated because no single reference discloses every feature.'
    );
    const rejectedAssessment = mountStoredReport(escapedStatusReason);
    assert.equal(rejectedAssessment.application.reportState.value, 'error');
    assert.match(
        rejectedAssessment.application.errorMessage.value,
        /must explain the evidence without repeating the assessment status/
    );

    const rawUpstreamResponse = {
        answer: JSON.stringify(validReport),
        info: { mode: 'graph_vector_fulltext', retrieved_nodes: 3 }
    };
    const reportCalls = [];
    const debugReport = mountReport({
        search: '?job_id=22222222-2222-4222-8222-222222222222',
        storage: new MemoryStorage(),
        fetchImplementation: async (url) => {
            reportCalls.push(url);
            if (url.endsWith('/raw')) {
                return jsonResponse(200, { upstream_response: rawUpstreamResponse });
            }
            return jsonResponse(200, { status: 'complete', data: validReport });
        }
    });
    await debugReport.intervalCallbacks.at(-1)();
    assert.deepEqual(reportCalls, [
        '/api/result/22222222-2222-4222-8222-222222222222',
        '/api/result/22222222-2222-4222-8222-222222222222/raw'
    ]);
    assert.equal(debugReport.application.reportState.value, 'complete');
    assert.deepEqual(
        JSON.parse(debugReport.application.rawResponseDetails.value),
        rawUpstreamResponse
    );
    assert.equal(debugReport.application.rawResponseExpanded.value, false);

    const normalReport = mountReport({
        search: '?job_id=33333333-3333-4333-8333-333333333333',
        storage: new MemoryStorage(),
        fetchImplementation: async (url) => {
            if (url.endsWith('/raw')) return jsonResponse(404, { error: 'Not found' });
            return jsonResponse(200, { status: 'complete', data: validReport });
        }
    });
    await normalReport.intervalCallbacks.at(-1)();
    assert.equal(normalReport.application.reportState.value, 'complete');
    assert.equal(normalReport.application.rawResponseDetails.value, '');

    const missingReport = mountReport({
        search: '?result_source=session-v2',
        storage: new MemoryStorage()
    });
    assert.equal(missingReport.application.reportState.value, 'error');
    assert.match(missingReport.application.errorMessage.value, /no longer available/);

    const serverErrorCalls = [];
    const serverError = mountSearch(async (url) => {
        serverErrorCalls.push(url);
        return jsonResponse(500, { error: 'Async service failed' });
    });
    serverError.application.documentText.value = 'Do not fall back on server failures';
    await serverError.application.submitQuery();
    assert.deepEqual(serverErrorCalls, ['/api/query']);
    assert.equal(serverError.window.location.href, '');
    assert.equal(serverError.application.status.value.message, 'Async service failed');

    console.log('Frontend sync fallback and session handoff passed');
}

run().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
