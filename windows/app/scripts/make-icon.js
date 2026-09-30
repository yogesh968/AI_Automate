// Renders the Jarvis orb icon as PNGs using only Node built-ins (zlib).
//   build/icon.png            512x512 (electron-builder makes the .ico from it)
//   build/icon-256.png        256x256
//   electron/assets/tray.png  32x32
//   electron/assets/icon.png  256x256 (window icon)
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function encodePNG(size, rgba) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0; // filter: none
    rgba.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const smooth = (e0, e1, x) => {
  const t = clamp((x - e0) / (e1 - e0));
  return t * t * (3 - 2 * t);
};

// Colour of one sample; coordinates in [-1, 1].
function sample(x, y) {
  const r = Math.hypot(x, y);
  let R = 0, G = 0, B = 0, A = 0;
  const over = (cr, cg, cb, ca) => {
    // "over" compositing with premultiplied accumulation
    R = cr * ca + R * (1 - ca);
    G = cg * ca + G * (1 - ca);
    B = cb * ca + B * (1 - ca);
    A = ca + A * (1 - ca);
  };

  // Soft outer glow
  const glow = Math.pow(clamp(1 - r / 0.98), 2.2) * 0.55;
  over(0.1, 0.75, 1.0, glow);

  // HUD ring with small gaps
  const ang = Math.atan2(y, x);
  const gap = Math.abs(Math.sin(ang * 3)) > 0.12 ? 1 : 0;
  const ring = smooth(0.035, 0.0, Math.abs(r - 0.84)) * gap;
  over(0.45, 0.92, 1.0, ring * 0.95);

  // Core sphere
  const core = smooth(0.66, 0.6, r);
  if (core > 0) {
    const z = Math.sqrt(clamp(1 - (r / 0.64) ** 2));
    // light from top-left
    const light = clamp(0.35 + 0.65 * (z * 0.8 + (-x * 0.35 - y * 0.45)));
    const fres = Math.pow(1 - z, 2.5);
    const cr = clamp(0.02 + 0.25 * light + 0.5 * fres);
    const cg = clamp(0.35 + 0.55 * light + 0.4 * fres);
    const cb = clamp(0.6 + 0.4 * light + 0.3 * fres);
    over(cr, cg, cb, core);
    // Hot centre
    const hot = Math.pow(clamp(1 - r / 0.32), 2) * core;
    over(0.9, 1.0, 1.0, hot * 0.85);
  }

  if (A <= 0) return [0, 0, 0, 0];
  return [R / A, G / A, B / A, A];
}

function render(size) {
  const buf = Buffer.alloc(size * size * 4);
  const ss = 3; // supersampling
  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      let r = 0, g = 0, b = 0, a = 0;
      for (let sy = 0; sy < ss; sy++) {
        for (let sx = 0; sx < ss; sx++) {
          const x = ((px + (sx + 0.5) / ss) / size) * 2 - 1;
          const y = ((py + (sy + 0.5) / ss) / size) * 2 - 1;
          const [cr, cg, cb, ca] = sample(x, y);
          r += cr * ca;
          g += cg * ca;
          b += cb * ca;
          a += ca;
        }
      }
      const n = ss * ss;
      const i = (py * size + px) * 4;
      const alpha = a / n;
      buf[i] = alpha > 0 ? Math.round((r / a) * 255) : 0;
      buf[i + 1] = alpha > 0 ? Math.round((g / a) * 255) : 0;
      buf[i + 2] = alpha > 0 ? Math.round((b / a) * 255) : 0;
      buf[i + 3] = Math.round(alpha * 255);
    }
  }
  return encodePNG(size, buf);
}

const root = path.resolve(__dirname, '..');
const outputs = [
  ['build/icon.png', 512],
  ['build/icon-256.png', 256],
  ['electron/assets/icon.png', 256],
  ['electron/assets/tray.png', 32],
];

for (const [rel, size] of outputs) {
  const file = path.join(root, rel);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, render(size));
  console.log(`wrote ${rel} (${size}x${size})`);
}
