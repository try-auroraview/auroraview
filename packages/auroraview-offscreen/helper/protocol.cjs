'use strict';

const MAX_COMMAND = 1024 * 1024;
const MAX_HEADER = 64 * 1024;
const MAX_PAYLOAD = 64 * 1024 * 1024;
const MAX_SURFACES = 8;
const ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;

function check(condition, message) {
  if (!condition) throw new Error(message);
}

function object(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function dimensions(width, height) {
  check(Number.isInteger(width) && width >= 1 && width <= 4096, 'width must be 1..4096');
  check(Number.isInteger(height) && height >= 1 && height <= 4096, 'height must be 1..4096');
}

function validateCommand(command) {
  check(object(command), 'command must be an object');
  if (command.type === 'shutdown') return command;
  check(ID.test(command.surface_id || ''), 'invalid surface_id');
  check(Number.isSafeInteger(command.generation) && command.generation >= 1, 'invalid generation');
  switch (command.type) {
    case 'create':
      dimensions(command.width, command.height);
      check((typeof command.html === 'string') !== (typeof command.url === 'string'),
        'create requires exactly one of html or url');
      if (command.url !== undefined) {
        check(['https:', 'http:', 'file:'].includes(new URL(command.url).protocol), 'unsupported URL protocol');
      }
      break;
    case 'resize':
      dimensions(command.width, command.height);
      break;
    case 'input': {
      const event = command.event;
      check(object(event), 'input requires event');
      const types = ['mouseMove', 'mouseDown', 'mouseUp', 'mouseWheel', 'keyDown', 'keyUp', 'text', 'focus'];
      check(types.includes(event.type), 'unsupported input type');
      if (event.type.startsWith('mouse')) {
        check(Number.isFinite(event.x) && Number.isFinite(event.y), 'mouse requires finite x/y');
        check(event.button === undefined || ['none', 'left', 'middle', 'right', 'back', 'forward'].includes(event.button),
          'invalid mouse button');
        check(event.buttons === undefined || (Number.isInteger(event.buttons) && event.buttons >= 0 && event.buttons <= 31),
          'invalid mouse buttons');
        check(event.click_count === undefined || (Number.isInteger(event.click_count) && event.click_count >= 0 && event.click_count <= 3),
          'invalid click_count');
        if (event.type === 'mouseWheel') {
          check(Number.isFinite(event.delta_x) && Number.isFinite(event.delta_y), 'wheel requires finite deltas');
        }
      } else if (event.type === 'text') {
        check(typeof event.text === 'string' && Buffer.byteLength(event.text) <= 65536, 'invalid text');
      } else if (event.type === 'focus') {
        check(typeof event.focused === 'boolean', 'focus requires focused boolean');
      } else {
        check(typeof event.key === 'string' && event.key.length <= 64, 'invalid key');
        check(event.code === undefined || (typeof event.code === 'string' && event.code.length <= 64), 'invalid code');
      }
      check(event.modifiers === undefined || (Number.isInteger(event.modifiers) && event.modifiers >= 0 && event.modifiers <= 15),
        'invalid modifiers');
      break;
    }
    case 'call_result':
      check(typeof command.id === 'string' && command.id.length > 0 && command.id.length <= 256, 'invalid call id');
      check(typeof command.ok === 'boolean', 'call_result requires ok boolean');
      if (!command.ok) check(object(command.error) && typeof command.error.message === 'string', 'missing call error');
      break;
    case 'emit':
      check(typeof command.event === 'string' && command.event.length > 0 && command.event.length <= 256, 'invalid event');
      break;
    case 'close':
      break;
    default:
      throw new Error('unsupported command type');
  }
  return command;
}

class LineDecoder {
  constructor(onCommand, onError) {
    this.pending = Buffer.alloc(0);
    this.onCommand = onCommand;
    this.onError = onError;
    this.discard = false;
  }

  push(chunk) {
    let start = 0;
    for (let end = 0; end < chunk.length; end++) {
      if (chunk[end] !== 10) continue;
      const part = chunk.subarray(start, end);
      if (!this.discard && this.pending.length + part.length <= MAX_COMMAND) {
        const line = Buffer.concat([this.pending, part]);
        if (line.length) {
          try { this.onCommand(validateCommand(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(line)))); }
          catch (error) { this.onError(error); }
        }
      } else if (!this.discard) this.onError(new Error('command exceeds 1 MiB'));
      this.pending = Buffer.alloc(0);
      this.discard = false;
      start = end + 1;
    }
    if (this.discard) return;
    const tail = chunk.subarray(start);
    if (this.pending.length + tail.length > MAX_COMMAND) {
      this.pending = Buffer.alloc(0);
      this.discard = true;
      this.onError(new Error('command exceeds 1 MiB'));
    } else if (tail.length) this.pending = Buffer.concat([this.pending, tail]);
  }
}

function encodeMessage(header, payload = Buffer.alloc(0)) {
  const json = Buffer.from(JSON.stringify(header), 'utf8');
  check(json.length <= MAX_HEADER, 'header exceeds 64 KiB');
  check(payload.length <= MAX_PAYLOAD, 'payload exceeds 64 MiB');
  const prefix = Buffer.alloc(8);
  prefix.writeUInt32LE(json.length, 0);
  prefix.writeUInt32LE(payload.length, 4);
  return Buffer.concat([prefix, json, payload]);
}

class FrameWriter {
  constructor(stream, onError) {
    this.stream = stream;
    this.onError = onError;
    this.control = [];
    this.frames = new Map();
    this.bytes = 0;
    this.busy = false;
    this.stopped = false;
    stream.on('error', onError);
  }

  send(header, payload = Buffer.alloc(0)) {
    if (this.stopped) return;
    const headerLength = Buffer.byteLength(JSON.stringify(header));
    check(headerLength <= MAX_HEADER, 'header exceeds 64 KiB');
    check(payload.length <= MAX_PAYLOAD, 'payload exceeds 64 MiB');
    const size = headerLength + payload.length + 8;
    check(size <= MAX_PAYLOAD + MAX_HEADER + 8, 'message too large');
    if (header.type === 'frame') {
      const key = `${header.surface_id}:${header.generation}`;
      const previous = this.frames.get(key);
      if (previous) this.bytes -= previous.size;
      this.frames.delete(key);
      while (this.bytes + size > MAX_PAYLOAD && this.frames.size) {
        const [oldKey, old] = this.frames.entries().next().value;
        this.frames.delete(oldKey);
        this.bytes -= old.size;
      }
      // One maximum-sized frame may occupy the frame mailbox on its own.
      if (this.bytes + size <= MAX_PAYLOAD + MAX_HEADER + 8) {
        this.frames.set(key, { header, payload, size });
        this.bytes += size;
      }
    } else {
      // RPC/events must remain deliverable when a large frame fills the
      // mailbox. Discard pending pixels before rejecting bounded controls.
      while (this.bytes + size > MAX_PAYLOAD && this.frames.size) {
        const [oldKey, old] = this.frames.entries().next().value;
        this.frames.delete(oldKey);
        this.bytes -= old.size;
      }
      check(this.control.length < 1024 && this.bytes + size <= MAX_PAYLOAD, 'output control queue full');
      this.control.push({ header, payload, size });
      this.bytes += size;
    }
    this.flush();
  }

  dropFrames(surfaceId, generation) {
    const key = `${surfaceId}:${generation}`;
    const old = this.frames.get(key);
    if (old) this.bytes -= old.size;
    this.frames.delete(key);
  }

  flush() {
    if (this.busy || this.stopped) return;
    let message = this.control.shift();
    if (!message && this.frames.size) {
      const [key, frame] = this.frames.entries().next().value;
      this.frames.delete(key);
      message = frame;
    }
    if (!message) return;
    this.bytes -= message.size;
    this.busy = true;
    this.stream.write(encodeMessage(message.header, message.payload), (error) => {
      this.busy = false;
      if (error) this.onError(error);
      else this.flush();
    });
  }

  idle() { return !this.busy && this.control.length === 0 && this.frames.size === 0; }
  stop() { this.stopped = true; this.frames.clear(); this.control.length = 0; this.bytes = 0; }
}

module.exports = { MAX_COMMAND, MAX_HEADER, MAX_PAYLOAD, MAX_SURFACES, dimensions,
  validateCommand, LineDecoder, encodeMessage, FrameWriter };
