'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { MAX_COMMAND, MAX_HEADER, MAX_PAYLOAD, validateCommand, LineDecoder, FrameWriter, encodeMessage } = require('../protocol.cjs');
const { toRgba } = require('../pixels.cjs');
const { keyEvent } = require('../input.cjs');

const create = { type: 'create', surface_id: 'tool-1', generation: 1, width: 320, height: 240, html: '<p>Hello</p>' };

test('commands validate dimensions, generations, content and native input fields', () => {
  assert.equal(validateCommand(create), create);
  for (const change of [{ width: 0 }, { height: 4097 }, { generation: 0 },
    { surface_id: '../bad' }, { html: undefined }, { url: 'https://example.com' }]) {
    assert.throws(() => validateCommand({ ...create, ...change }));
  }
  assert.throws(() => validateCommand({ ...create, html: undefined, url: 'javascript:alert(1)' }));
  assert.throws(() => validateCommand({ ...create, type: 'eval', script: 'process.exit()' }));
  assert.throws(() => validateCommand({ ...create, type: 'input', event: { type: 'mouseDown', x: Infinity, y: 0 } }));
  assert.throws(() => validateCommand({ ...create, type: 'input', event: { type: 'text', text: 'x', modifiers: 16 } }));
  assert.throws(() => validateCommand({ ...create, type: 'input', event: { type: 'focus', focused: 1 } }));
  assert.equal(validateCommand({ type: 'shutdown' }).type, 'shutdown');
  assert.doesNotThrow(() => validateCommand({ ...create, type: 'input',
    event: { type: 'mouseUp', x: -50, y: 9000, buttons: 0 } }));
});

test('physical DOM codes preserve shortcut keys and numpad identity independently of Unicode text', () => {
  assert.equal(keyEvent({ type: 'keyDown', key: '中', code: 'KeyA', modifiers: 2 }).windowsVirtualKeyCode, 65);
  assert.equal(keyEvent({ type: 'keyDown', key: '+', code: 'Equal' }).windowsVirtualKeyCode, 187);
  const keypad = keyEvent({ type: 'keyUp', key: '1', code: 'Numpad1' });
  assert.equal(keypad.windowsVirtualKeyCode, 97);
  assert.equal(keypad.location, 3);
  assert.equal(keypad.isKeypad, true);
  assert.equal(keypad.type, 'keyUp');
  assert.equal(keyEvent({ type: 'keyDown', key: 'F24', code: 'F24' }).windowsVirtualKeyCode, 135);
  assert.equal(keyEvent({ type: 'keyDown', key: 'ArrowLeft', code: 'ArrowLeft' }).location, 0);
  assert.equal(keyEvent({ type: 'keyUp', key: 'Control', code: 'ControlRight' }).location, 2);
});

test('line decoder handles split UTF-8, malformed lines and oversized-line recovery', () => {
  const commands = [];
  const errors = [];
  const decoder = new LineDecoder((command) => commands.push(command), (error) => errors.push(error.message));
  const line = Buffer.from(JSON.stringify({ ...create, html: '中文' }) + '\n');
  for (const byte of line) decoder.push(Buffer.from([byte]));
  decoder.push(Buffer.from('{broken}\n'));
  decoder.push(Buffer.from([0xff, 10]));
  decoder.push(Buffer.alloc(MAX_COMMAND + 1, 120));
  decoder.push(Buffer.from('ignored\n{"type":"shutdown"}\n'));
  assert.equal(commands.length, 2);
  assert.equal(commands[0].html, '中文');
  assert.equal(commands[1].type, 'shutdown');
  assert.equal(errors.length, 3);
});

function decode(buffer) {
  const headerSize = buffer.readUInt32LE(0);
  const payloadSize = buffer.readUInt32LE(4);
  assert.equal(buffer.length, 8 + headerSize + payloadSize);
  return { header: JSON.parse(buffer.subarray(8, 8 + headerSize)), payload: buffer.subarray(8 + headerSize) };
}

test('binary envelope has exact little-endian lengths and header bounds', () => {
  const bytes = Buffer.from([0, 255, 23]);
  const message = decode(encodeMessage({ type: 'frame', seq: 2 }, bytes));
  assert.deepEqual(message.payload, bytes);
  assert.equal(message.header.seq, 2);
  assert.throws(() => encodeMessage({ value: 'x'.repeat(MAX_HEADER) }));
});

class SlowStream extends EventEmitter {
  constructor() { super(); this.messages = []; this.callbacks = []; }
  write(bytes, callback) { this.messages.push(decode(bytes)); this.callbacks.push(callback); return false; }
  release() { this.callbacks.shift()(); }
}

test('backpressure keeps only latest frame and preserves control priority/order', () => {
  const stream = new SlowStream();
  const writer = new FrameWriter(stream, (error) => { throw error; });
  const frame = (seq) => ({ type: 'frame', surface_id: 'one', generation: 1, seq });
  writer.send(frame(1), Buffer.from([1]));
  writer.send(frame(2), Buffer.from([2]));
  writer.send(frame(3), Buffer.from([3]));
  writer.send({ type: 'call', id: 'a' });
  writer.send({ type: 'event', event: 'b' });
  assert.equal(writer.frames.size, 1);
  stream.release();
  stream.release();
  stream.release();
  stream.release();
  assert.deepEqual(stream.messages.map((item) => item.header.type), ['frame', 'call', 'event', 'frame']);
  assert.equal(stream.messages[3].header.seq, 3);
  assert.ok(writer.idle());
  assert.throws(() => writer.send({ type: 'event', detail: 'x'.repeat(MAX_HEADER) }));
});

test('closing a generation drops its queued pixels without dropping another surface', () => {
  const stream = new SlowStream();
  const writer = new FrameWriter(stream, (error) => { throw error; });
  writer.send({ type: 'ready' });
  writer.send({ type: 'frame', surface_id: 'one', generation: 1 });
  writer.send({ type: 'frame', surface_id: 'two', generation: 1 });
  writer.dropFrames('one', 1);
  stream.release();
  stream.release();
  assert.equal(stream.messages[1].header.surface_id, 'two');
  assert.ok(writer.idle());
});

test('control messages displace pending maximum-size pixels while output is blocked', () => {
  const stream = new SlowStream();
  const writer = new FrameWriter(stream, (error) => { throw error; });
  writer.send({ type: 'ready' });
  writer.send({ type: 'frame', surface_id: 'large', generation: 1 }, Buffer.alloc(MAX_PAYLOAD));
  assert.doesNotThrow(() => writer.send({ type: 'call', id: 'reply-needed' }));
  assert.equal(writer.frames.size, 0);
  stream.release();
  stream.release();
  assert.deepEqual(stream.messages.map((message) => message.header.type), ['ready', 'call']);
  assert.ok(writer.idle());
});

test('native premultiplied BGRA is normalized to straight RGBA with top-left origin', () => {
  const bytes = Buffer.from([32, 64, 112, 128, 255, 10, 20, 255, 99, 99, 99, 0, 30, 20, 10, 255]);
  const rgba = toRgba(bytes, 2, 2, { channels: [2, 1, 0, 3], premultiplied: true, flipped: false });
  assert.deepEqual([...rgba], [223, 128, 64, 128, 20, 10, 255, 255, 0, 0, 0, 0, 10, 20, 30, 255]);
  assert.throws(() => toRgba(bytes, 1, 1, { channels: [0, 1, 2, 3] }));
  const flipped = toRgba(Buffer.from([4, 5, 6, 255, 1, 2, 3, 255]), 1, 2,
    { channels: [0, 1, 2, 3], premultiplied: false, flipped: true });
  assert.deepEqual([...flipped], [1, 2, 3, 255, 4, 5, 6, 255]);
});
