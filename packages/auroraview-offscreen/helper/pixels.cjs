'use strict';

const { deflateSync } = require('node:zlib');

function crc32(bytes) {
  let crc = -1;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ -1) >>> 0;
}

function pngChunk(type, data) {
  const name = Buffer.from(type);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([name, data])));
  return Buffer.concat([length, name, data, crc]);
}

function calibrationPng() {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(1);
  header.writeUInt32BE(2, 4);
  header[8] = 8;
  header[9] = 6;
  const rows = Buffer.from([0, 17, 67, 149, 255, 0, 224, 128, 64, 128]);
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk('IHDR', header), pngChunk('IDAT', deflateSync(rows)), pngChunk('IEND', Buffer.alloc(0))]);
}

// NativeImage documents platform-dependent bitmap layout. Calibrate the actual
// pinned runtime with a known sRGB PNG instead of guessing its channel order.
function calibrate(nativeImage) {
  const image = nativeImage.createFromBuffer(calibrationPng());
  const bytes = image.toBitmap({ scaleFactor: 1 });
  if (bytes.length !== 8) throw new Error('unexpected native bitmap calibration size');
  const top = bytes.subarray(0, 4);
  const flipped = !top.includes(255);
  const opaque = bytes.subarray(flipped ? 4 : 0, flipped ? 8 : 4);
  const channels = [17, 67, 149, 255].map((value) => opaque.indexOf(value));
  if (channels.includes(-1)) throw new Error('unsupported native bitmap channel layout');
  const translucent = bytes.subarray(flipped ? 0 : 4, flipped ? 4 : 8);
  const alpha = translucent[channels[3]];
  if (alpha !== 128) throw new Error('unsupported native bitmap alpha layout');
  const red = translucent[channels[0]];
  const premultiplied = Math.abs(red * 255 / alpha - 224) <= 2;
  if (!premultiplied && Math.abs(red - 224) > 2) throw new Error('unsupported native bitmap alpha mode');
  return { channels, premultiplied, flipped };
}

function toRgba(bitmap, width, height, layout) {
  if (bitmap.length !== width * height * 4) throw new Error('bitmap length does not match dimensions');
  const rgba = Buffer.allocUnsafe(bitmap.length);
  const [red, green, blue, alpha] = layout.channels;
  const stride = width * 4;
  for (let row = 0; row < height; row++) {
    const sourceRow = layout.flipped ? height - row - 1 : row;
    for (let column = 0; column < stride; column += 4) {
      const from = sourceRow * stride + column;
      const to = row * stride + column;
      const a = bitmap[from + alpha];
      const factor = layout.premultiplied && a > 0 ? 255 / a : 1;
      rgba[to] = a ? Math.min(255, Math.round(bitmap[from + red] * factor)) : 0;
      rgba[to + 1] = a ? Math.min(255, Math.round(bitmap[from + green] * factor)) : 0;
      rgba[to + 2] = a ? Math.min(255, Math.round(bitmap[from + blue] * factor)) : 0;
      rgba[to + 3] = a;
    }
  }
  return rgba;
}

module.exports = { calibrate, toRgba, calibrationPng };
