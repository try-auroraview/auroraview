'use strict';

const { app, BrowserWindow, ipcMain, nativeImage } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const { LineDecoder, FrameWriter, MAX_COMMAND, MAX_SURFACES, MAX_HEADER } = require('./protocol.cjs');
const { calibrate, toRgba } = require('./pixels.cjs');
const { keyEvent } = require('./input.cjs');

// This process owns Chromium's loop; Blender never pumps it or hosts a native
// browser window. All browser operations below run on Electron's main thread.
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('force-device-scale-factor', '1');
app.commandLine.appendSwitch('disable-background-timer-throttling');

const surfaces = new Map();
const generations = new Map();
let closing = false;
let layout;
let bridgeSource;
let logicalFocus = null;
const channelPath = process.env.AURORAVIEW_OFFSCREEN_PIPE;
const channelSecret = process.env.AURORAVIEW_OFFSCREEN_SECRET;
if (!channelPath || !/^[a-f0-9]{64}$/.test(channelSecret || '')) {
  process.stderr.write('Launch through helper/stdio.cjs in Electron RUN_AS_NODE mode\n');
  app.exit(1);
}
const profile = process.env.AURORAVIEW_OFFSCREEN_PROFILE;
if (!profile || !path.isAbsolute(profile)) {
  process.stderr.write('private renderer profile missing\n');
  app.exit(1);
}
// Separate renderer processes must never contend for Chromium's disk caches,
// cookies, local storage or profile locks. Multiple surfaces share one process.
app.setPath('userData', profile);
app.setPath('sessionData', profile);
const channel = net.createConnection({ path: channelPath, allowHalfOpen: true });
channel.write(Buffer.from(channelSecret, 'hex'));

function identity(surface) {
  return { surface_id: surface.id, generation: surface.generation };
}

function report(error, command) {
  const header = { type: 'error', code: 'RENDERER_ERROR', message: String(error.message || error).slice(0, 4096) };
  if (command && typeof command.surface_id === 'string') {
    header.surface_id = command.surface_id;
    header.generation = command.generation;
  }
  try { writer.send(header); }
  catch (failure) { process.stderr.write(`${failure.message}\n`); shutdown(false); }
}

const writer = new FrameWriter(channel, (error) => {
  process.stderr.write(`${error.message}\n`);
  shutdown(false);
});

function readBridge() {
  const paths = [path.join(__dirname, 'event_bridge.js'),
    path.resolve(__dirname, '../../auroraview-sdk/dist/inject/event_bridge.js')];
  const file = paths.find((candidate) => fs.existsSync(candidate));
  if (!file) throw new Error('SDK injection asset missing: build @auroraview/sdk and bundle event_bridge.js');
  return fs.readFileSync(file, 'utf8') + '\n' +
    'window.ipc.onMessage(function(message) {' +
    ' window.auroraview.trigger(message.event, message.detail); });';
}

function requireSurface(command) {
  const surface = surfaces.get(command.surface_id);
  if (!surface || surface.generation !== command.generation || surface.window.isDestroyed()) {
    throw new Error('surface is closed or generation is stale');
  }
  return surface;
}

function deliver(surface, event, detail) {
  surface.window.webContents.send('auroraview:delivery', { event, detail });
}

function paint(surface, image) {
  if (!surface.painting || surface.window.isDestroyed() || closing) return;
  const size = image.getSize(1);
  // A resize can deliver an older compositor frame. Never label old pixels as
  // the newly accepted viewport revision.
  const [nativeWidth, nativeHeight] = surface.window.getContentSize();
  if (size.width !== nativeWidth || size.height !== nativeHeight ||
      size.width < surface.width || size.height < surface.height) return;
  // Windows enforces a small native-window minimum, even for hidden OSR.
  // CDP fixes the CSS viewport; crop only that current native backing image.
  if (size.width !== surface.width || size.height !== surface.height) {
    image = image.crop({ x: 0, y: 0, width: surface.width, height: surface.height });
  }
  const bitmap = image.toBitmap({ scaleFactor: 1 });
  const rgba = toRgba(bitmap, surface.width, surface.height, layout);
  writer.send({ type: 'frame', ...identity(surface), seq: ++surface.seq,
    resize_revision: surface.revision, width: surface.width, height: surface.height,
    stride: surface.width * 4, format: 'rgba8', alpha: 'straight', origin: 'top-left' }, rgba);
}

async function create(command) {
  if (surfaces.has(command.surface_id)) throw new Error('surface_id already exists');
  if (surfaces.size >= MAX_SURFACES) throw new Error('maximum 8 live surfaces');
  if (command.generation <= (generations.get(command.surface_id) || 0)) throw new Error('generation must increase');
  if (!generations.has(command.surface_id) && generations.size >= 1024) throw new Error('surface identity limit reached');

  const win = new BrowserWindow({ width: command.width, height: command.height,
    show: false, focusable: false, skipTaskbar: true, frame: false,
    webPreferences: { offscreen: { useSharedTexture: false },
      backgroundThrottling: false, nodeIntegration: false, contextIsolation: true,
      sandbox: true, disableDialogs: true, preload: path.join(__dirname, 'preload.cjs') } });
  win.setMenu(null);
  win.setMinimumSize(1, 1);
  win.setContentSize(command.width, command.height);
  const surface = { id: command.surface_id, generation: command.generation, window: win,
    width: command.width, height: command.height, revision: 0, seq: 0,
    painting: false, pending: new Set() };
  surfaces.set(surface.id, surface);
  generations.set(surface.id, surface.generation);
  win.on('focus', () => {
    report(new Error('hidden helper window unexpectedly received native focus'), command);
    shutdown(false);
  });
  win.on('closed', () => {
    if (surfaces.get(surface.id) === surface) surfaces.delete(surface.id);
    if (logicalFocus === surface) logicalFocus = null;
    writer.dropFrames(surface.id, surface.generation);
    surface.pending.clear();
    writer.send({ type: 'closed', ...identity(surface) });
  });
  const contents = win.webContents;
  if (process.env.AURORAVIEW_RENDERER_TRACE) {
    contents.on('console-message', (details) => process.stderr.write(`page: ${details.message}\n`));
    contents.on('preload-error', (_event, _file, error) => process.stderr.write(`preload: ${error.message}\n`));
  }
  contents.setWindowOpenHandler(() => ({ action: 'deny' }));
  contents.on('render-process-gone', (_event, details) => {
    report(new Error(`renderer process exited: ${details.reason}`), command);
    if (!win.isDestroyed()) win.destroy();
  });
  contents.on('paint', (_event, _dirty, image) => {
    try { paint(surface, image); }
    catch (error) { report(error, command); }
  });
  contents.setFrameRate(20);
  try {
    // Establish a live target before awaiting CDP commands. No TCP debugging
    // endpoint, visible BrowserWindow, focus() or nested event loop is used.
    await contents.loadURL('about:blank');
    contents.debugger.attach('1.3');
    contents.debugger.on('detach', (_event, reason) => {
      if (!closing && surfaces.get(surface.id) === surface && !win.isDestroyed()) {
        report(new Error(`input debugger detached: ${reason}`), command);
        win.destroy();
      }
    });
    await contents.debugger.sendCommand('Page.enable');
    await contents.debugger.sendCommand('Emulation.setDeviceMetricsOverride', {
      width: command.width, height: command.height, deviceScaleFactor: 1, mobile: false,
    });
    await contents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', { source: bridgeSource, runImmediately: true });
    await focus(surface, true);
    const url = command.url || `data:text/html;charset=utf-8,${encodeURIComponent(command.html)}`;
    let loadTimeout;
    try {
      await Promise.race([contents.loadURL(url), new Promise((_, reject) => {
        loadTimeout = setTimeout(() => reject(new Error('surface load timed out')), 15000);
      })]);
    } finally { clearTimeout(loadTimeout); }
    if (closing || win.isDestroyed()) return;
    surface.painting = true;
    contents.startPainting();
    writer.send({ type: 'ready', ...identity(surface), protocol: 1,
      width: surface.width, height: surface.height, resize_revision: 0,
      visible: win.isVisible(), focused: win.isFocused() });
    contents.invalidate();
  } catch (error) {
    if (!win.isDestroyed()) win.destroy();
    throw error;
  }
}

async function focus(surface, enabled) {
  if (enabled && logicalFocus && logicalFocus !== surface && !logicalFocus.window.isDestroyed()) {
    await logicalFocus.window.webContents.debugger.sendCommand('Emulation.setFocusEmulationEnabled', { enabled: false });
  }
  await surface.window.webContents.debugger.sendCommand('Emulation.setFocusEmulationEnabled', { enabled });
  logicalFocus = enabled ? surface : (logicalFocus === surface ? null : logicalFocus);
}

async function input(surface, event) {
  if (event.type === 'focus') return focus(surface, event.focused);
  if (logicalFocus !== surface) await focus(surface, true);
  const debuggerApi = surface.window.webContents.debugger;
  if (event.type === 'text') return debuggerApi.sendCommand('Input.insertText', { text: event.text });
  if (event.type.startsWith('mouse')) {
    const types = { mouseMove: 'mouseMoved', mouseDown: 'mousePressed', mouseUp: 'mouseReleased', mouseWheel: 'mouseWheel' };
    const params = { type: types[event.type], x: event.x, y: event.y,
      button: event.button || 'none', buttons: event.buttons || 0,
      modifiers: event.modifiers || 0, clickCount: event.click_count || 0 };
    if (event.type === 'mouseDown' || event.type === 'mouseUp') {
      params.button = event.button || 'left';
      params.clickCount = event.click_count || 1;
    }
    if (event.type === 'mouseWheel') {
      params.deltaX = event.delta_x;
      params.deltaY = event.delta_y;
    }
    return debuggerApi.sendCommand('Input.dispatchMouseEvent', params);
  }
  return debuggerApi.sendCommand('Input.dispatchKeyEvent', keyEvent(event));
}

async function handle(command) {
  if (closing) return;
  if (command.type === 'shutdown') { shutdown(true); return; }
  if (command.type === 'create') { await create(command); return; }
  const surface = requireSurface(command);
  const contents = surface.window.webContents;
  switch (command.type) {
    case 'resize':
      surface.painting = false;
      surface.width = command.width;
      surface.height = command.height;
      surface.revision++;
      writer.dropFrames(surface.id, surface.generation);
      surface.window.setContentSize(command.width, command.height);
      await contents.debugger.sendCommand('Emulation.setDeviceMetricsOverride', {
        width: command.width, height: command.height, deviceScaleFactor: 1, mobile: false,
      });
      await contents.debugger.sendCommand('Page.getLayoutMetrics');
      surface.painting = true;
      contents.invalidate();
      break;
    case 'input':
      await input(surface, command.event);
      break;
    case 'call_result':
      if (!surface.pending.delete(command.id)) throw new Error('unknown or completed call id');
      deliver(surface, '__auroraview_call_result', {
        id: command.id, ok: command.ok, result: command.result, error: command.error });
      break;
    case 'emit':
      deliver(surface, command.event, command.detail);
      break;
    case 'close':
      surface.painting = false;
      contents.stopPainting();
      surface.window.destroy();
      break;
  }
}

ipcMain.on('auroraview:bridge', (event, message) => {
  const surface = [...surfaces.values()].find((item) => item.window.webContents === event.sender);
  if (!surface || closing) return;
  let call;
  try {
    if (typeof message !== 'string' || Buffer.byteLength(message) > MAX_COMMAND) throw new Error('bridge message too large');
    const payload = JSON.parse(message);
    if (payload.type === 'call' || payload.type === 'invoke') {
      call = payload;
      if (typeof payload.id !== 'string' || !payload.id || payload.id.length > 256) throw new Error('invalid bridge call id');
      if (payload.type === 'invoke') throw new Error('native plugin commands are not supported by this renderer');
      if (typeof payload.method !== 'string' || !payload.method || payload.method.length > 256) throw new Error('invalid bridge method');
      if (surface.pending.has(payload.id) || surface.pending.size >= 256) throw new Error('bridge call queue full or duplicate id');
      const header = { type: 'call', ...identity(surface), id: payload.id,
        method: payload.method, params: payload.params };
      if (Buffer.byteLength(JSON.stringify(header)) > MAX_HEADER) throw new Error('bridge call header exceeds 64 KiB');
      surface.pending.add(payload.id);
      writer.send(header);
    } else if (payload.type === 'event') {
      if (typeof payload.event !== 'string' || !payload.event || payload.event.length > 256) throw new Error('invalid bridge event');
      writer.send({ type: 'event', ...identity(surface), event: payload.event, detail: payload.detail });
    } else throw new Error('unsupported bridge message');
  } catch (error) {
    if (call && typeof call.id === 'string') {
      surface.pending.delete(call.id);
      deliver(surface, '__auroraview_call_result', { id: call.id, ok: false,
        error: { name: 'RendererError', message: error.message, code: 'UNSUPPORTED_OR_INVALID_CALL' } });
    } else report(error, identity(surface));
  }
});

function shutdown(flush) {
  if (closing) return;
  if (process.env.AURORAVIEW_RENDERER_TRACE) process.stderr.write(`shutdown flush=${flush}\n`);
  closing = true;
  channel.pause();
  for (const surface of [...surfaces.values()]) {
    if (!surface.window.isDestroyed()) surface.window.destroy();
  }
  const deadline = Date.now() + (flush ? 2000 : 0);
  function finish() {
    if (flush && !writer.idle() && Date.now() < deadline) { setTimeout(finish, 10); return; }
    writer.stop();
    if (process.env.AURORAVIEW_RENDERER_TRACE) process.stderr.write('renderer exiting\n');
    app.exit(0);
  }
  finish();
}

channel.pause();
channel.on('end', () => {
  if (process.env.AURORAVIEW_RENDERER_TRACE) process.stderr.write('stdin EOF\n');
  shutdown(false);
});
if (process.env.AURORAVIEW_RENDERER_TRACE) app.on('will-quit', () => process.stderr.write('app will quit\n'));
process.on('SIGTERM', () => shutdown(false));
app.on('window-all-closed', () => {}); // Surfaces may be recreated until explicit shutdown/EOF.
app.whenReady().then(() => {
  layout = calibrate(nativeImage);
  bridgeSource = readBridge();
  let queued = 0;
  let chain = Promise.resolve();
  const decoder = new LineDecoder((command) => {
    if (process.env.AURORAVIEW_RENDERER_TRACE) process.stderr.write(`command ${command.type}\n`);
    if (command.type === 'shutdown') { shutdown(true); return; }
    if (++queued > 128) { report(new Error('command queue exceeds 128')); shutdown(false); return; }
    chain = chain.then(() => handle(command)).catch((error) => report(error, command)).finally(() => queued--);
  }, (error) => report(error));
  channel.on('data', (chunk) => decoder.push(chunk));
  writer.send({ type: 'ready', protocol: 1, electron: process.versions.electron, pid: process.pid });
  channel.resume();
}).catch((error) => { report(error); shutdown(true); });
