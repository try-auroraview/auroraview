'use strict';

// Electron's Windows GUI process does not preserve a readable Node stdin.
// Run this launcher with the same Electron binary in RUN_AS_NODE mode. It owns
// stdio and bridges a private authenticated local pipe to the hidden GUI process.
const net = require('node:net');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');

const secret = crypto.randomBytes(32);
const temporaryRoot = fs.realpathSync(os.tmpdir());
const directory = fs.mkdtempSync(path.join(temporaryRoot, 'auroraview-'));
if (process.platform !== 'win32') fs.chmodSync(directory, 0o700);
const endpoint = process.platform === 'win32'
  ? `\\\\.\\pipe\\auroraview-${crypto.randomUUID()}` : path.join(directory, 'renderer.sock');
let child;
let connection;
let attached = false;
let ended = false;
let started = false;
let startLine = Buffer.alloc(0);
const server = net.createServer({ allowHalfOpen: true }, (socket) => {
  if (attached) { socket.destroy(); return; }
  let prefix = Buffer.alloc(0);
  const timeout = setTimeout(() => socket.destroy(), 5000);
  socket.on('error', () => {});
  socket.on('data', function authenticate(chunk) {
    const needed = secret.length - prefix.length;
    prefix = Buffer.concat([prefix, chunk.subarray(0, needed)]);
    if (prefix.length !== secret.length) return;
    clearTimeout(timeout);
    socket.removeListener('data', authenticate);
    if (!crypto.timingSafeEqual(prefix, secret)) { socket.destroy(); return; }
    attached = true;
    connection = socket;
    clearTimeout(startup);
    server.close();
    socket.pipe(process.stdout);
    if (chunk.length > needed) process.stdout.write(chunk.subarray(needed));
    process.stdin.pipe(socket);
    if (ended) socket.end();
  });
});

function cleanup() {
  clearTimeout(startup);
  process.stdin.unpipe();
  process.stdin.pause();
  server.close();
  if (connection) connection.destroy();
  // The profile is created by this broker, never accepted from commands.
  const resolved = path.resolve(directory);
  if (path.dirname(resolved) === temporaryRoot && path.basename(resolved).startsWith('auroraview-')) {
    try { fs.rmSync(resolved, { recursive: true, force: true, maxRetries: 3, retryDelay: 30 }); }
    catch (error) { process.stderr.write(`owned profile cleanup: ${error.message}\n`); }
  }
}

const startup = setTimeout(() => {
  process.stderr.write('renderer channel startup timed out\n');
  if (child) child.kill();
  cleanup();
  process.exitCode = 1;
}, 15000);
server.on('error', (error) => {
  process.stderr.write(`${error.message}\n`);
  if (child) child.kill();
  cleanup();
  process.exitCode = 1;
});
function launch() {
  const env = { ...process.env, AURORAVIEW_OFFSCREEN_PIPE: endpoint,
    AURORAVIEW_OFFSCREEN_SECRET: secret.toString('hex'),
    AURORAVIEW_OFFSCREEN_PROFILE: directory, ELECTRON_NO_ATTACH_CONSOLE: '1' };
  delete env.ELECTRON_RUN_AS_NODE;
  child = spawn(process.execPath, [__dirname], { env, windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'] });
  // Native GUI bootstrap diagnostics, including its Windows CRLF, never enter
  // the public binary protocol stream.
  child.stdout.pipe(process.stderr, { end: false });
  child.stderr.pipe(process.stderr, { end: false });
  child.on('error', (error) => { process.stderr.write(`${error.message}\n`); cleanup(); process.exitCode = 1; });
  child.on('exit', (code) => {
    if (process.env.AURORAVIEW_RENDERER_TRACE) process.stderr.write(`renderer exited code=${code}\n`);
    child.stdout.destroy();
    child.stderr.destroy();
    cleanup();
    process.exitCode = code || 0;
  });
}
server.listen(endpoint, () => {
  process.stdin.on('data', function start(chunk) {
    startLine = Buffer.concat([startLine, chunk]);
    const newline = startLine.indexOf(10);
    if (newline > 1024 || (newline < 0 && startLine.length > 1024)) {
      process.stderr.write('invalid launcher start line\n'); cleanup(); process.exitCode = 1; return;
    }
    if (newline < 0) return;
    let command;
    try { command = JSON.parse(startLine.subarray(0, newline)); } catch {}
    if (!command || command.type !== 'start') {
      process.stderr.write('launcher start command required\n'); cleanup(); process.exitCode = 1; return;
    }
    started = true;
    process.stdin.removeListener('data', start);
    process.stdin.pause();
    if (startLine.length > newline + 1) process.stdin.unshift(startLine.subarray(newline + 1));
    startLine = Buffer.alloc(0);
    launch();
  });
});
process.stdin.on('end', () => {
  ended = true;
  if (connection) connection.end();
  else if (!started) { cleanup(); process.exitCode = 0; }
});
process.stdout.on('error', () => { if (child) child.kill(); cleanup(); });
process.on('SIGTERM', () => { if (child) child.kill(); cleanup(); });
