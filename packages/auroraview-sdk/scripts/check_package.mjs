// Consume the npm archive outside the checkout; do not import SDK source files.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync,
  rmSync, statSync, writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const script = fileURLToPath(import.meta.url);
const json = (file) => JSON.parse(readFileSync(file, 'utf8'));
const sha256 = (file) => createHash('sha256').update(readFileSync(file)).digest('hex');
const inside = (parent, child) => {
  const relative = path.relative(parent, child);
  return relative === '' || (!relative.startsWith(`..${path.sep}`)
    && relative !== '..' && !path.isAbsolute(relative));
};

function run(args, cwd, timeout = 60_000) {
  return execFileSync('vx', args, {
    cwd, encoding: 'utf8', timeout, maxBuffer: 4 * 1024 * 1024,
    env: { ...process.env, NODE_PATH: '' },
  });
}

async function consume() {
  const require = createRequire(import.meta.url);
  const entry = require.resolve('@auroraview/sdk');
  const packageRoot = realpathSync(path.dirname(path.dirname(entry)));
  assert(inside(path.dirname(script), packageRoot), 'SDK must be installed in the consumer');
  const metadata = json(path.join(packageRoot, 'package.json'));
  const exports = [];
  for (const [subpath, conditions] of Object.entries(metadata.exports)) {
    const specifier = metadata.name + (subpath === '.' ? '' : subpath.slice(1));
    const targets = typeof conditions === 'string' ? [conditions] : Object.values(conditions);
    for (const target of targets) {
      assert.equal(typeof target, 'string', `Unsupported export target: ${subpath}`);
      const installed = realpathSync(path.resolve(packageRoot, target));
      assert(inside(packageRoot, installed), `Export escapes installed package: ${target}`);
      assert(statSync(installed).isFile(), `Missing export: ${target}`);
    }
    const esm = fileURLToPath(import.meta.resolve(specifier));
    const cjs = require.resolve(specifier);
    assert(inside(packageRoot, realpathSync(esm)));
    assert(inside(packageRoot, realpathSync(cjs)));
    if (typeof conditions === 'object') {
      assert.equal(esm, path.resolve(packageRoot, conditions.import));
      assert.equal(cjs, path.resolve(packageRoot, conditions.require));
    }
    exports.push({ subpath, targets, import: esm, require: cjs });
  }
  assert(metadata.exports['./inject/event-bridge'], 'Missing public injection export');

  // Optional framework peers are intentionally absent. Resolve their entries,
  // but execute the framework-independent root in genuine Node SSR conditions.
  assert.equal(typeof globalThis.window, 'undefined');
  assert.equal(typeof globalThis.document, 'undefined');
  const esm = await import('@auroraview/sdk');
  const cjs = require('@auroraview/sdk');
  assert.deepEqual(Object.keys(esm).sort(), Object.keys(cjs).sort());
  for (const sdk of [esm, cjs]) {
    assert.equal(sdk.isAuroraView(), false);
  }

  const checks = ['all-export-targets', 'esm-cjs-resolution', 'esm-ssr', 'cjs-ssr'];
  const listeners = new Map();
  const timers = new Set();
  const messages = [];
  const errors = [];
  let name = 'Before';
  const window = {
    location: { href: 'https://package.invalid/' },
    addEventListener(event, callback) {
      const handlers = listeners.get(event) ?? [];
      handlers.push(callback);
      listeners.set(event, handlers);
    },
    dispatchEvent(event) {
      for (const callback of listeners.get(event.type) ?? []) callback(event);
    },
    ipc: { postMessage(raw) {
      const message = JSON.parse(raw);
      messages.push(message);
      if (message.type !== 'call' || message.method === 'tools.never') return;
      let reply;
      if (message.method === 'tools.rename') {
        name = message.params.name;
        reply = { id: message.id, ok: true, result: { name } };
      } else if (message.method === 'tools.read') {
        reply = { id: message.id, ok: true, result: { name } };
      } else {
        reply = { id: message.id, ok: false, error: {
          name: 'ValidationError', message: 'Invalid tool input', code: 'INVALID_PARAMS',
          data: { field: 'name' },
        } };
      }
      queueMicrotask(() => window.auroraview.trigger('__auroraview_call_result', reply));
    } },
  };
  const context = vm.createContext({
    window, document: { readyState: 'complete', addEventListener() {} },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    console: { log() {}, debug() {}, warn() {}, error: (...args) => errors.push(args) },
    setTimeout(callback, delay) {
      const timer = setTimeout(() => { timers.delete(timer); callback(); }, delay);
      timers.add(timer);
      return timer;
    },
    clearTimeout(timer) { timers.delete(timer); clearTimeout(timer); },
    setInterval() { throw new Error('Unexpected heartbeat interval'); },
    clearInterval() {},
  });
  const bridgeFile = fileURLToPath(import.meta.resolve('@auroraview/sdk/inject/event-bridge'));
  try {
    new vm.Script(readFileSync(bridgeFile, 'utf8'), { filename: bridgeFile })
      .runInContext(context, { timeout: 1_000 });
    globalThis.window = window;
    const client = cjs.createAuroraView();
    assert.equal(client.isReady(), true);
    assert.equal(window.auroraview.isReady(), true);
    checks.push('packaged-injection-ready');
    const renamed = await client.call('tools.rename', { name: 'PackageVerified' });
    assert.deepEqual(renamed, { name: 'PackageVerified' });
    assert.deepEqual(await client.call('tools.read'), renamed);
    const request = messages.find((message) => message.method === 'tools.rename');
    assert.equal(request.type, 'call');
    assert.equal(typeof request.id, 'string');
    assert.deepEqual(request.params, { name: 'PackageVerified' });
    checks.push('sdk-ipc-call-reply-readback');

    let received = 0;
    const dispose = client.on('scene.changed', () => { received += 1; });
    window.auroraview.trigger('scene.changed', { revision: 1 });
    assert.equal(received, 1);
    dispose();
    window.auroraview.trigger('scene.changed', { revision: 2 });
    assert.equal(received, 1);
    client.emit('consumer.saved', { name });
    assert.deepEqual(messages.at(-1), { type: 'event', event: 'consumer.saved', detail: { name } });
    checks.push('sdk-event-dispose', 'sdk-outbound-event');

    await assert.rejects(client.call('tools.invalid'), (error) => {
      assert.equal(error.name, 'ValidationError');
      assert.equal(error.message, 'Invalid tool input');
      assert.equal(error.code, 'INVALID_PARAMS');
      assert.deepEqual(error.data, { field: 'name' });
      return true;
    });
    checks.push('structured-error');
    window.auroraview.setConfig({ callTimeoutMs: 25 });
    await assert.rejects(client.call('tools.never'), (error) => error.code === 'TIMEOUT'
      && error.name === 'TimeoutError');
    checks.push('timeout');
    const pending = client.call('tools.never');
    const cancelled = assert.rejects(pending, (error) => error.code === 'CANCELLED');
    window.dispatchEvent({ type: 'beforeunload' });
    await cancelled;
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(timers.size, 0, 'All injected pending-call timers must be released');
    assert.deepEqual(errors, []);
    checks.push('js-pending-call-unload-cancellation', 'timer-cleanup');
  } finally {
    delete globalThis.window;
    for (const timer of timers) clearTimeout(timer);
  }
  return { package: metadata.name, version: metadata.version, node: process.version, exports, checks,
    bridge_sha256: sha256(bridgeFile), optional_framework_peers_executed: false };
}

function pack() {
  const outputIndex = process.argv.indexOf('--output');
  const output = path.resolve(outputIndex < 0 ? 'package-artifacts' : process.argv[outputIndex + 1]);
  mkdirSync(output, { recursive: true });
  const receiptFile = path.join(output, 'sdk-package-receipt.json');
  const receipt = { generated_utc: new Date().toISOString(), status: 'failed',
    stage: 'initializing', node: process.version,
    offline_install: true, native_host: false, ui: false,
    native_cancellation_validated: false };
  // Invalidate any previous success before build checks, packing or temp setup.
  writeFileSync(receiptFile, `${JSON.stringify(receipt, null, 2)}\n`);
  let failure;
  let temporaryRoot;
  let consumer;
  try {
    receipt.stage = 'build-check';
    const repository = realpathSync(path.resolve(path.dirname(script), '../../..'));
    const packageRoot = path.join(repository, 'packages/auroraview-sdk');
    assert(existsSync(path.join(packageRoot, 'dist/inject/event_bridge.js')), 'Build SDK first');
    receipt.stage = 'pack';
    const packed = JSON.parse(run(['npm', 'pack', '--ignore-scripts', '--json',
      '--pack-destination', output], packageRoot))[0];
    const tarball = path.join(output, packed.filename);
    assert(inside(output, tarball));
    receipt.tarball = { filename: packed.filename, size: statSync(tarball).size,
      sha256: sha256(tarball), integrity: packed.integrity, shasum: packed.shasum };
    receipt.packed_files = packed.files.map((file) => file.path);
    receipt.stage = 'consumer-setup';
    temporaryRoot = realpathSync(tmpdir());
    consumer = mkdtempSync(path.join(temporaryRoot, 'auroraview-sdk-consumer-'));
    receipt.consumer_directory = consumer;
    assert(!inside(repository, realpathSync(consumer)), 'Consumer must be outside the checkout');
    writeFileSync(path.join(consumer, 'package.json'), JSON.stringify({ private: true, type: 'module' }));
    receipt.stage = 'offline-install';
    run(['npm', 'install', '--offline', '--ignore-scripts', '--legacy-peer-deps',
      '--no-audit', '--no-fund', '--no-package-lock', tarball], consumer);
    copyFileSync(script, path.join(consumer, 'consumer.mjs'));
    receipt.stage = 'consumer-check';
    receipt.consumer = JSON.parse(run(['node@22', 'consumer.mjs', '--consumer'], consumer, 20_000));
  } catch (error) {
    failure = error;
    receipt.error = error.message;
  } finally {
    if (consumer) {
      try {
        // Delete only the resolved, newly-created directory owned by this run.
        const target = realpathSync(consumer);
        assert(inside(temporaryRoot, target) && target !== temporaryRoot);
        assert(path.basename(target).startsWith('auroraview-sdk-consumer-'));
        rmSync(target, { recursive: true, force: true });
        receipt.consumer_removed = !existsSync(target);
        assert(receipt.consumer_removed, 'Consumer cleanup did not complete');
      } catch (error) {
        if (!failure) receipt.stage = 'cleanup';
        failure ??= error;
        receipt.cleanup_error = error.message;
        receipt.consumer_removed = false;
      }
    }
    receipt.status = failure ? 'failed' : 'passed';
    if (!failure) receipt.stage = 'complete';
    try {
      writeFileSync(receiptFile, `${JSON.stringify(receipt, null, 2)}\n`);
    } catch (error) {
      // The initial failed receipt remains if final persistence fails.
      failure ??= error;
      receipt.status = 'failed';
      receipt.receipt_error = error.message;
    }
  }
  console.log(JSON.stringify(receipt, null, 2));
  if (failure) throw failure;
}

if (process.argv.includes('--consumer')) {
  console.log(JSON.stringify(await consume()));
} else {
  pack();
}
