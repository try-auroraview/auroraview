'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const { MAX_HEADER, MAX_PAYLOAD } = require('../protocol.cjs');

const executable = process.env.AURORAVIEW_ELECTRON;
if (!executable) throw new Error('AURORAVIEW_ELECTRON must point to the verified Electron executable');

function fixture(nonce) {
  return `<!doctype html><meta charset="utf-8"><style>
    html,body{margin:0;background:rgb(12,34,56);color:white;font:14px sans-serif}
    body{height:1200px}input{position:absolute;left:20px;top:20px;width:160px;height:30px}
    button{position:absolute;left:20px;top:70px;width:120px;height:32px}
    </style><input id="text"><button id="button">Count</button><script>
    let count=0; const input=document.getElementById('text');
    const send=(event,detail)=>auroraview.send_event(event,detail);
    input.addEventListener('input',()=>send('typed',{value:input.value}));
    document.getElementById('button').onclick=()=>send('clicked',{count:++count});
    window.addEventListener('scroll',()=>send('scrolled',{y:scrollY}));
    window.addEventListener('keyup',e=>send('key',{key:e.key,code:e.code,location:e.location}));
    auroraview.on('probe',detail=>send('state',{nonce:detail.nonce,value:input.value,
      active:document.activeElement.id,width:innerWidth,height:innerHeight,scroll:scrollY,count}));
    auroraview.call('test.echo',{nonce:${JSON.stringify(nonce)}})
      .then(result=>send('roundtrip',result)).catch(error=>send('rpc-error',{message:error.message}));
    auroraview.invoke('fs:read_file',{path:'unavailable'})
      .catch(error=>send('unsupported',{code:error.code}));
    </script>`;
}

class Renderer extends EventEmitter {
  constructor() {
    super();
    const env = { ...process.env };
    env.ELECTRON_NO_ATTACH_CONSOLE = '1';
    env.AURORAVIEW_RENDERER_TRACE = '1';
    env.ELECTRON_RUN_AS_NODE = '1';
    this.child = spawn(executable, [path.resolve(__dirname, '../stdio.cjs')], {
      env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.messages = [];
    this.frames = new Map();
    this.pending = Buffer.alloc(0);
    this.stderr = '';
    this.failure = null;
    this.child.stderr.on('data', (chunk) => { this.stderr = (this.stderr + chunk).slice(-16000); });
    this.child.on('error', (error) => { this.failure = error; this.emit('change'); });
    this.exited = new Promise((resolve) => this.child.once('exit', (code, signal) => {
      this.exit = { code, signal }; this.emit('change'); resolve(this.exit);
    }));
    this.child.stdout.on('data', (chunk) => {
      try {
        this.pending = Buffer.concat([this.pending, chunk]);
        while (this.pending.length >= 8) {
          const headerLength = this.pending.readUInt32LE(0);
          const payloadLength = this.pending.readUInt32LE(4);
          assert.ok(headerLength <= MAX_HEADER && payloadLength <= MAX_PAYLOAD,
            `bounded helper envelope ${this.pending.subarray(0, 12).toString('hex')}: ${this.pending.subarray(0, 240).toString('utf8')}; stderr=${this.stderr}`);
          const total = 8 + headerLength + payloadLength;
          if (this.pending.length < total) break;
          const header = JSON.parse(this.pending.subarray(8, 8 + headerLength));
          if (header.type === 'frame') {
            const payload = Buffer.from(this.pending.subarray(8 + headerLength, total));
            assert.equal(payload.length, header.width * header.height * 4);
            assert.equal(header.stride, header.width * 4);
            assert.equal(header.format, 'rgba8');
            assert.equal(header.alpha, 'straight');
            assert.equal(header.origin, 'top-left');
            const previous = this.frames.get(header.surface_id);
            if (previous && previous.header.generation === header.generation) assert.ok(header.seq > previous.header.seq);
            this.frames.set(header.surface_id, { header, payload });
          }
          this.messages.push(header);
          if (this.messages.length > 1000) this.messages.shift();
          if (header.type === 'call' && header.method === 'test.echo') {
            this.send({ type: 'call_result', surface_id: header.surface_id, generation: header.generation,
              id: header.id, ok: true, result: { echoed: header.params.nonce } });
          }
          this.pending = this.pending.subarray(total);
          this.emit('change');
        }
      } catch (error) { this.failure = error; this.emit('change'); }
    });
    this.send({ type: 'start' });
  }

  send(command) {
    if (command.type === 'shutdown') this.shutdownAt = Date.now();
    this.child.stdin.write(JSON.stringify(command) + '\n');
  }

  async wait(predicate, timeout = 15000) {
    const deadline = Date.now() + timeout;
    while (true) {
      if (this.failure) throw this.failure;
      const value = predicate();
      if (value) return value;
      if (this.exit) throw new Error(`helper exited ${JSON.stringify(this.exit)}; events=${JSON.stringify(this.messages.slice(-8))}; stderr=${this.stderr}`);
      if (Date.now() >= deadline) throw new Error(`native helper timeout; events=${JSON.stringify(this.messages.slice(-8))}; stderr=${this.stderr}`);
      await new Promise((resolve) => {
        const timer = setTimeout(done, Math.min(250, deadline - Date.now()));
        const self = this;
        function done() { clearTimeout(timer); self.removeListener('change', done); resolve(); }
        self.once('change', done);
      });
    }
  }

  event(event, predicate = () => true, surfaceId = 'primary') {
    return this.wait(() => this.messages.find((message) => message.type === 'event' &&
      message.surface_id === surfaceId && message.event === event && predicate(message.detail)));
  }

  async exitWithin(timeout = 4000) {
    let timer;
    try {
      const result = await Promise.race([this.exited, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`helper did not shut down; exit=${JSON.stringify(this.exit)}; stderr=${this.stderr}`)), timeout);
      })]);
      assert.equal(result.code, 0, this.stderr);
      assert.doesNotMatch(this.stderr, /Unable to (?:move|create) (?:the )?cache|Cache Creation failed|owned profile cleanup/);
      this.shutdownMilliseconds = Date.now() - this.shutdownAt;
      return result;
    } finally { clearTimeout(timer); }
  }

  kill() {
    if (this.exit) return;
    // Smoke tests own this broker PID and its entire descendant tree. Windows
    // child.kill() alone terminates the broker without running SIGTERM hooks.
    if (process.platform === 'win32') {
      const result = spawnSync('taskkill.exe', ['/PID', String(this.child.pid), '/T', '/F'],
        { windowsHide: true, encoding: 'utf8' });
      this.cleanup = { owned_pid: this.child.pid, action: 'taskkill /T /F',
        status: result.status, stdout: result.stdout, stderr: result.stderr };
      process.stderr.write(`owned smoke cleanup: ${JSON.stringify(this.cleanup)}\n`);
    } else this.child.kill();
  }
}

test('real hidden CPU renderer paints, routes native CDP input and reuses SDK RPC', { timeout: 60000 }, async (t) => {
  const renderer = new Renderer();
  t.after(() => renderer.kill());
  const handshake = await renderer.wait(() => renderer.messages.find((message) => message.type === 'ready' && !message.surface_id));
  assert.equal(handshake.protocol, 1);
  const base = { surface_id: 'primary', generation: 1 };
  const sendInput = (event) => renderer.send({ type: 'input', ...base, event });
  const click = (x, y) => {
    sendInput({ type: 'mouseDown', x, y, button: 'left', buttons: 1, click_count: 1 });
    sendInput({ type: 'mouseUp', x, y, button: 'left', buttons: 0, click_count: 1 });
  };
  renderer.send({ type: 'create', ...base, width: 320, height: 240, html: fixture('first') });
  const surfaceReady = await renderer.wait(() => renderer.messages.find((message) => message.type === 'ready' && message.surface_id === 'primary'));
  assert.equal(surfaceReady.visible, false);
  assert.equal(surfaceReady.focused, false);
  const initial = await renderer.wait(() => {
    const frame = renderer.frames.get('primary');
    return frame && frame.payload[0] === 12 && frame;
  });
  assert.deepEqual([...initial.payload.subarray(0, 4)], [12, 34, 56, 255]);
  assert.equal(initial.header.resize_revision, 0);
  await renderer.event('roundtrip', (detail) => detail.echoed === 'first');
  await renderer.event('unsupported', (detail) => detail.code === 'UNSUPPORTED_OR_INVALID_CALL');

  click(60, 35);
  sendInput({ type: 'text', text: '中文 Hello' });
  await renderer.event('typed', (detail) => detail.value === '中文 Hello');
  sendInput({ type: 'keyDown', key: 'a', code: 'KeyA', modifiers: 2 });
  sendInput({ type: 'keyUp', key: 'a', code: 'KeyA', modifiers: 2 });
  sendInput({ type: 'text', text: 'Z' });
  await renderer.event('typed', (detail) => detail.value === 'Z');
  sendInput({ type: 'keyDown', key: 'Backspace', code: 'Backspace' });
  sendInput({ type: 'keyUp', key: 'Backspace', code: 'Backspace' });
  await renderer.event('typed', (detail) => detail.value === '');
  sendInput({ type: 'keyDown', key: 'ArrowLeft', code: 'ArrowLeft' });
  sendInput({ type: 'keyUp', key: 'ArrowLeft', code: 'ArrowLeft' });
  await renderer.event('key', (detail) => detail.code === 'ArrowLeft' && detail.location === 0);
  sendInput({ type: 'keyDown', key: '1', code: 'Numpad1' });
  sendInput({ type: 'keyUp', key: '1', code: 'Numpad1' });
  await renderer.event('key', (detail) => detail.code === 'Numpad1' && detail.location === 3);
  sendInput({ type: 'keyDown', key: 'Tab', code: 'Tab' });
  sendInput({ type: 'keyUp', key: 'Tab', code: 'Tab' });
  renderer.send({ type: 'emit', ...base, event: 'probe', detail: { nonce: 'tab' } });
  await renderer.event('state', (detail) => detail.nonce === 'tab' && detail.active === 'button');
  click(60, 85);
  await renderer.event('clicked', (detail) => detail.count === 1);
  sendInput({ type: 'mouseWheel', x: 280, y: 150, delta_x: 0, delta_y: 180 });
  await renderer.event('scrolled', (detail) => detail.y > 0);

  renderer.send({ type: 'resize', ...base, width: 480, height: 300 });
  const resized = await renderer.wait(() => {
    const frame = renderer.frames.get('primary');
    return frame && frame.header.width === 480 && frame.header.height === 300 && frame.header.resize_revision === 1 && frame;
  });
  renderer.send({ type: 'resize', ...base, width: 480, height: 300 });
  await renderer.wait(() => renderer.frames.get('primary')?.header.resize_revision === 2);
  renderer.send({ type: 'emit', ...base, event: 'probe', detail: { nonce: 'resized' } });
  await renderer.event('state', (detail) => detail.nonce === 'resized' && detail.width === 480 && detail.height === 300);

  renderer.send({ type: 'create', surface_id: 'secondary', generation: 1, width: 200, height: 120, html: fixture('second') });
  await renderer.event('roundtrip', (detail) => detail.echoed === 'second', 'secondary');
  await renderer.wait(() => renderer.frames.get('secondary'));
  sendInput({ type: 'focus', focused: false });
  renderer.send({ type: 'close', ...base });
  await renderer.wait(() => renderer.messages.find((message) => message.type === 'closed' && message.surface_id === 'primary'));
  renderer.send({ type: 'create', surface_id: 'primary', generation: 2, width: 160, height: 100, html: fixture('recreated') });
  await renderer.event('roundtrip', (detail) => detail.echoed === 'recreated');
  renderer.send({ type: 'emit', ...base, event: 'probe', detail: { nonce: 'stale' } });
  await renderer.wait(() => renderer.messages.find((message) => message.type === 'error' && /generation is stale/.test(message.message)));
  const unexpected = renderer.messages.filter((message) => message.type === 'error' && !/generation is stale/.test(message.message));
  assert.deepEqual(unexpected, []);
  const readiness = renderer.messages.filter((message) => message.type === 'ready' && message.surface_id);
  assert.ok(readiness.every((message) => message.visible === false && message.focused === false));
  renderer.send({ type: 'shutdown' });
  await renderer.exitWithin();
  const report = { electron: handshake.electron, helper_pid: handshake.pid, protocol: 1,
    hidden_windows: true, native_focus_events: 0, paint: true, rgba_pixel: [12, 34, 56, 255],
    committed_unicode: true, ctrl_a: true, backspace: true, tab: true, click: true,
    scroll: true, resize: [resized.header.width, resized.header.height], resize_revision: 2,
    sdk_roundtrip: true, host_event: true, multiple_surfaces: true, generation_isolation: true,
    shutdown: true, shutdown_ms: renderer.shutdownMilliseconds };
  if (process.env.AURORAVIEW_SMOKE_REPORT) {
    fs.mkdirSync(path.dirname(process.env.AURORAVIEW_SMOKE_REPORT), { recursive: true });
    fs.writeFileSync(process.env.AURORAVIEW_SMOKE_REPORT, JSON.stringify(report, null, 2));
  }
  t.diagnostic(JSON.stringify(report));
});

test('parent stdin EOF closes a live hidden renderer without another command', { timeout: 25000 }, async (t) => {
  const renderer = new Renderer();
  t.after(() => renderer.kill());
  // Sending before ready is intentional: stdin is buffered until app readiness.
  renderer.send({ type: 'create', surface_id: 'early', generation: 1, width: 80, height: 60,
    html: '<body style="background:rgb(1,2,3)">EOF<script>auroraview.send_event("size",{width:innerWidth,height:innerHeight})</script>' });
  await renderer.wait(() => renderer.frames.get('early'));
  await renderer.event('size', (detail) => detail.width === 80 && detail.height === 60, 'early');
  renderer.send({ type: 'resize', surface_id: 'early', generation: 1, width: 1, height: 1 });
  await renderer.wait(() => renderer.frames.get('early')?.header.width === 1 &&
    renderer.frames.get('early')?.header.height === 1 && renderer.frames.get('early')?.header.resize_revision === 1);
  renderer.shutdownAt = Date.now();
  renderer.child.stdin.end();
  await renderer.exitWithin();
  t.diagnostic(JSON.stringify({ owned_pid: renderer.child.pid, parent_eof: true,
    shutdown_ms: renderer.shutdownMilliseconds, exit_code: renderer.exit.code }));
});

test('concurrent renderer owners isolate profiles and both exit on parent EOF', { timeout: 25000 }, async (t) => {
  const renderers = [new Renderer(), new Renderer()];
  t.after(() => renderers.forEach((renderer) => renderer.kill()));
  await Promise.all(renderers.map(async (renderer, index) => {
    renderer.send({ type: 'create', surface_id: 'owned', generation: 1, width: 80, height: 60,
      html: `<body style="background:rgb(${index + 1},2,3)">Concurrent</body>` });
    await renderer.wait(() => renderer.frames.get('owned'));
  }));
  await Promise.all(renderers.map(async (renderer) => {
    renderer.shutdownAt = Date.now();
    renderer.child.stdin.end();
    await renderer.exitWithin();
  }));
  t.diagnostic(JSON.stringify({ isolated_profiles: true, owned_processes: renderers.map((renderer) =>
    ({ pid: renderer.child.pid, exit_code: renderer.exit.code, shutdown_ms: renderer.shutdownMilliseconds })) }));
});
