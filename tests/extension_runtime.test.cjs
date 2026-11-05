// Full content script, isolated VM, tiny DOM adapter, fake clock and mocked
// fetch. This tests behavior, not Chrome layout, OAuth or the current ChatGPT DOM.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../extension/content.js'), 'utf8');
assert.match(source, /\nstartBetterPrompt\(\);\s*$/);
const withoutBoot = source.replace(/\nstartBetterPrompt\(\);\s*$/, '\n');

class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.parentElement = null;
    this.attributes = {}; this.listeners = {}; this.style = {}; this.disabled = false;
    const classes = new Set();
    this.classList = {
      add: (...names) => names.forEach(x => classes.add(x)),
      remove: (...names) => names.forEach(x => classes.delete(x)),
      toggle: (name, force) => force ? classes.add(name) : classes.delete(name)
    };
  }
  set textContent(value) { this.children.forEach(x => x.parentElement = null); this.children = []; this.text = value; }
  get textContent() { return (this.text || '') + this.children.map(x => x.textContent).join(''); }
  get firstChild() { return this.children[0] || null; }
  get isConnected() { return this.tagName === 'body' || Boolean(this.parentElement?.isConnected); }
  appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
  removeChild(child) { this.children = this.children.filter(x => x !== child); child.parentElement = null; }
  remove() { this.parentElement?.removeChild(this); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(name, callback, options) { (this.listeners[name] ||= []).push({ callback, once: options?.once }); }
  click() {
    if (this.disabled) return;
    const events = [...(this.listeners.click || [])];
    this.listeners.click = events.filter(x => !x.once);
    events.forEach(x => x.callback());
  }
  focus() {}
  dispatchEvent() {}
  querySelector(selector) {
    const match = x => selector[0] === '#' ? x.id === selector.slice(1) :
      /^\[data-action="/.test(selector) && x.attributes['data-action'] === selector.slice(14, -2);
    for (const child of this.children) {
      if (match(child)) return child;
      const nested = child.querySelector(selector); if (nested) return nested;
    }
    return null;
  }
}
class Textarea extends Element {
  constructor() { super('textarea'); this._value = ''; }
  set value(text) { this._value = text; }
  get value() { return this._value; }
}
const flush = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };

function harness(plans = {}) {
  let now = 0, id = 0;
  const timers = new Map(), calls = [];
  const window = {
    HTMLTextAreaElement: Textarea,
    setTimeout(fn, ms) { const key = ++id; timers.set(key, { at: now + ms, fn }); return key; },
    clearTimeout(key) { timers.delete(key); }
  };
  function delayed(value, ms, signal, rejectValue = false) {
    return new Promise((resolve, reject) => {
      const abort = () => { window.clearTimeout(key); reject(new DOMException('Aborted', 'AbortError')); };
      const key = window.setTimeout(() => {
        signal?.removeEventListener('abort', abort);
        rejectValue ? reject(value) : resolve(value);
      }, ms);
      signal?.addEventListener('abort', abort, { once: true });
      if (signal?.aborted) abort();
    });
  }
  const body = new Element('body');
  const context = vm.createContext({
    window, console: { log() {}, warn() {}, error() {}, debug() {} },
    URL, AbortController, DOMException, Error, Element, HTMLElement: Element,
    HTMLButtonElement: Element, HTMLTextAreaElement: Textarea,
    Event: class {}, InputEvent: class {}, chrome: {},
    document: {
      body, createElement: tag => tag === 'textarea' ? new Textarea() : new Element(tag),
      querySelector: selector => body.querySelector(selector)
    },
    BETTER_PROMPT_CONFIG: { apiBaseUrl: 'https://fixture.invalid', apiUrl: 'https://fixture.invalid/improve' },
    fetch(url, options) {
      const route = new URL(url).pathname;
      calls.push({ route, method: options.method, body: options.body, headers: options.headers });
      let plan = plans[route];
      if (Array.isArray(plan)) plan = plan.shift();
      plan ||= {};
      if (plan.error) return delayed(plan.error, plan.delay || 0, options.signal, true);
      const payload = plan.payload ?? (route === '/health' ? { status: 'ok' } :
        { issues: [], improved_prompt: '설명을 더 명확하게 해 주세요.' });
      return delayed({
        ok: !plan.status || plan.status < 400, status: plan.status || 200,
        json: () => delayed(payload, plan.bodyDelay || 0, options.signal, Boolean(plan.badJson)),
        text: () => delayed(JSON.stringify(payload), plan.bodyDelay || 0, options.signal)
      }, plan.delay || 0, options.signal);
    }
  });
  vm.runInContext(withoutBoot, context);
  return {
    context, calls, body, timers,
    request(options) { return context.requestPromptImprovement('짧은 질문', options); },
    session() { return vm.runInContext('activeAnalysisSession', context); },
    input(value = '이 코드를 설명해 줘') { const input = new Textarea(); input.value = value; body.appendChild(input); return input; },
    async advance(ms) {
      const target = now + ms;
      await flush();
      while (true) {
        const next = [...timers].filter(([, t]) => t.at <= target).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        now = next[1].at; timers.delete(next[0]); next[1].fn(); await flush();
      }
      now = target; await flush();
    }
  };
}
const observe = promise => {
  const state = {};
  promise.then(value => Object.assign(state, { value, done: true }), error => Object.assign(state, { error, done: true }));
  return state;
};

test('cold readiness at 60s succeeds, then exactly one improve request', async () => {
  const h = harness({ '/health': { delay: 60000 }, '/improve': { delay: 1000 } });
  const stages = [];
  const state = observe(h.request({ onStage: stage => stages.push(stage) }));
  await h.advance(59999);
  assert.equal(h.calls.length, 1); assert.equal(state.done, undefined);
  await h.advance(1001);
  assert.equal(state.value.improved_prompt, '설명을 더 명확하게 해 주세요.');
  assert.deepEqual(stages, ['preparing', 'analyzing']);
  assert.deepEqual(h.calls.map(x => x.route), ['/health', '/improve']);
  assert.equal(h.timers.size, 0);
});

test('preparation deadline sends zero paid requests', async () => {
  const h = harness({ '/health': { delay: 80000 } });
  const state = observe(h.request()); await h.advance(75000);
  assert.match(state.error.message, /AI 개선 요청은 보내지 않았습니다/);
  assert.equal(h.calls.filter(x => x.route === '/improve').length, 0);
  assert.equal(h.timers.size, 0);
});

test('failed readiness never falls through to improve', async () => {
  for (const plan of [{ status: 503, payload: { detail: '준비 중' } }, { payload: { status: 'starting' } }, { badJson: true }]) {
    const h = harness({ '/health': plan }); const state = observe(h.request()); await h.advance(0);
    assert.ok(state.error); assert.equal(h.calls.length, 1);
  }
});

test('deadline covers hanging response body', async () => {
  const h = harness({ '/improve': { bodyDelay: 80000 } });
  const state = observe(h.request()); await h.advance(70000);
  assert.match(state.error.message, /대기 시간이 지났습니다/);
  assert.equal(h.calls.filter(x => x.route === '/improve').length, 1);
  assert.equal(h.timers.size, 0);
});

test('cancel during preparation prevents improve', async () => {
  const h = harness({ '/health': { delay: 60000 } }); const controller = new AbortController();
  const state = observe(h.request({ signal: controller.signal }));
  await h.advance(1000); controller.abort(); await h.advance(0);
  assert.equal(state.error.name, 'AbortError'); assert.equal(h.calls.length, 1);
  assert.equal(h.timers.size, 0);
});

test('already cancelled request does not progress to improve', async () => {
  const h = harness(); const controller = new AbortController(); controller.abort();
  const state = observe(h.request({ signal: controller.signal })); await h.advance(0);
  assert.equal(state.error.name, 'AbortError'); assert.equal(h.calls.length, 0);
});

test('invalid improvement body cannot become an applicable result', async () => {
  for (const payload of [null, {}, { issues: [], improved_prompt: '' }, { issues: [], improved_prompt: 3 },
                         { issues: [{}], improved_prompt: 'x' }]) {
    const h = harness({ '/improve': { payload: payload === null ? false : payload } });
    const state = observe(h.request()); await h.advance(0);
    assert.ok(state.error); assert.equal(h.calls.length, 2);
  }
});

test('HTTP errors are visible with no automatic improve retry', async () => {
  const h = harness({ '/improve': { status: 502, payload: { detail: 'AI 응답 처리 실패' } } });
  const state = observe(h.request()); await h.advance(0);
  assert.equal(state.error.message, 'AI 응답 처리 실패'); assert.equal(h.calls.length, 2);
});

test('improvement carries the service session, never the Google access token', async () => {
  const h = harness();
  vm.runInContext('authState = {sessionToken: "synthetic-service-session", user: null};', h.context);
  const state = observe(h.request()); await h.advance(0);
  assert.ok(state.value);
  assert.equal(h.calls.find(x => x.route === '/improve').headers.Authorization, 'Bearer synthetic-service-session');
  assert.equal(h.calls.find(x => x.route === '/health').headers, undefined);
});

test('short question can complete; applying result changes input only on click', async () => {
  const h = harness(); const input = h.input(); const original = input.value;
  h.context.handleBetterPromptClick(input); await h.advance(0);
  const parts = h.session().popupParts;
  assert.equal(parts.applyButton.disabled, false); assert.equal(input.value, original);
  parts.applyButton.click();
  assert.equal(input.value, '설명을 더 명확하게 해 주세요.'); assert.equal(h.session(), null);
});

test('editing input during analysis prevents stale result replacing it', async () => {
  const h = harness({ '/improve': { delay: 2000 } }); const input = h.input();
  h.context.handleBetterPromptClick(input); await h.advance(1000); input.value = '새로 작성한 요청';
  await h.advance(1000); const parts = h.session().popupParts; parts.applyButton.click();
  assert.equal(input.value, '새로 작성한 요청'); assert.match(parts.resultsContainer.textContent, /프롬프트가 바뀌었습니다/);
  assert.equal(parts.applyButton.disabled, true);
});

test('closing while waiting aborts the request and preserves input', async () => {
  const h = harness({ '/health': { delay: 60000 } }); const input = h.input(); const original = input.value;
  h.context.handleBetterPromptClick(input); await h.advance(1000);
  assert.equal(h.session().popupParts.keepButton.textContent, '취소');
  h.session().popupParts.keepButton.click(); await h.advance(60000);
  assert.equal(input.value, original); assert.equal(h.session(), null); assert.equal(h.calls.length, 1);
  assert.equal(h.body.querySelector('#better-prompt-popup'), null);
});

test('cancellation during improve also aborts local response handling', async () => {
  const h = harness({ '/improve': { delay: 60000 } }); const input = h.input(); const original = input.value;
  h.context.handleBetterPromptClick(input); await h.advance(1000);
  h.session().popupParts.keepButton.click(); await h.advance(60000);
  assert.equal(input.value, original); assert.equal(h.session(), null); assert.equal(h.calls.length, 2);
});

test('failed analysis keeps apply disabled and offers a deliberate retry', async () => {
  const h = harness({ '/improve': [{ status: 502, payload: { detail: 'AI 처리 실패' } }, {}] });
  const input = h.input(); h.context.handleBetterPromptClick(input); await h.advance(0);
  const parts = h.session().popupParts;
  assert.equal(parts.applyButton.disabled, true); assert.match(parts.resultsContainer.textContent, /AI 처리 실패/);
  assert.doesNotMatch(parts.resultsContainer.textContent, /충분히 좋은/);
  const retry = parts.resultsContainer.children.find(x => x.attributes['data-action'] === 'retry');
  assert.ok(retry); retry.click(); await h.advance(0);
  assert.equal(h.session().popupParts.applyButton.disabled, false);
  assert.equal(h.calls.filter(x => x.route === '/improve').length, 2);
});
