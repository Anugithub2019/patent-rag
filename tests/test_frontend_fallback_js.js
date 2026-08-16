'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const validReport = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'fixtures', 'analysis-v2.valid.json'), 'utf8')
);

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

function mountSearch(fetchImplementation) {
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
        fetch: fetchImplementation,
        console: { error() {} }
    });

    return { application, storage, window };
}

function mountReport({ search, storage }) {
    let application;
    const mountedCallbacks = [];
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
        setInterval: () => 1,
        clearInterval() {},
        fetch: async () => {
            throw new Error('The session-result path must not poll the job API');
        },
        console: { error() {}, warn() {} }
    });

    return { application, window };
}

async function run() {
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
