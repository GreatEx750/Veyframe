import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
import sharp from 'sharp';

const directory = path.dirname(fileURLToPath(import.meta.url));
const width = 2560;
const height = 1440;
const slots = {
  video: { x: 52, y: 153, width: 2016, height: 1134, radius: 22 },
  presenter: { x: 2128, y: 392, width: 369, height: 656, radius: 24 },
};
const rect = (slot, attributes = '') => `<rect x="${slot.x}" y="${slot.y}" width="${slot.width}" height="${slot.height}" rx="${slot.radius}" ${attributes}/>`;
const shell = (body, extra = '') => `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
  <linearGradient id="pastel" x2="1" y2="0.7"><stop stop-color="#DADAF0"/><stop offset="0.56" stop-color="#E9EDD7"/><stop offset="1" stop-color="#EEE5D8"/></linearGradient>
  <radialGradient id="blush"><stop stop-color="#F7DADF" stop-opacity="0.95"/><stop offset="1" stop-color="#F7DADF" stop-opacity="0"/></radialGradient>
  <radialGradient id="mint"><stop stop-color="#E7F4CD" stop-opacity="0.8"/><stop offset="1" stop-color="#E7F4CD" stop-opacity="0"/></radialGradient>
  <linearGradient id="video-fill" x2="1" y2="1"><stop stop-color="#4532FF"/><stop offset="1" stop-color="#6938FE"/></linearGradient>
  <linearGradient id="presenter-fill" x2="0.6" y2="1"><stop stop-color="#D3CFCA"/><stop offset="1" stop-color="#AEA69F"/></linearGradient>
  <filter id="shadow" x="-30%" y="-30%" width="160%" height="180%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="25"/></filter>
  <mask id="openings"><rect width="2560" height="1440" fill="white"/>${Object.values(slots).map(s => rect(s, 'fill="black"')).join('')}</mask>
  ${extra}
</defs>${body}</svg>`;

const scenery = `<rect width="2560" height="1440" fill="url(#pastel)"/>
<g>
  <ellipse cx="1550" cy="1360" rx="1160" ry="760" fill="url(#blush)"/>
  <ellipse cx="2140" cy="245" rx="940" ry="680" fill="url(#mint)"/>
  <g transform="translate(0 30)" filter="url(#shadow)" fill="#342344" opacity="0.24">${Object.values(slots).map(s => rect(s)).join('')}</g>
</g>
<path d="M2310 96h88" stroke="white" stroke-width="8" stroke-linecap="square"/>`;

await mkdir(directory, { recursive: true });
const overlay = shell(`<g mask="url(#openings)">${scenery}</g>`);
const background = shell(scenery);
const preview = shell(`${scenery}
${rect(slots.video, 'fill="url(#video-fill)"')}
${rect(slots.presenter, 'fill="url(#presenter-fill)"')}
<g fill="white" font-family="Arial, sans-serif" text-anchor="middle">
  <text x="${slots.video.x + slots.video.width / 2}" y="732" font-size="34" opacity="0.8">Video</text>
  <text x="${slots.presenter.x + slots.presenter.width / 2}" y="731" font-size="30" opacity="0.85">Presenter</text>
</g>`);
for (const [name, svg] of Object.entries({ overlay, background, preview })) {
  await writeFile(path.join(directory, `${name}.svg`), svg);
  await sharp(Buffer.from(svg)).png().toFile(path.join(directory, `${name}.png`));
}
for (const [name, slot] of Object.entries(slots)) {
  const svg = shell(`<rect width="2560" height="1440" fill="black"/>${rect(slot, 'fill="white"')}`);
  await sharp(Buffer.from(svg)).removeAlpha().png().toFile(path.join(directory, `${name}-mask.png`));
}
await writeFile(path.join(directory, 'layout.json'), JSON.stringify({
  id: 'presenter-split-v1', status: 'standalone_not_integrated',
  canvas: { width, height }, suggested_duration_seconds: 40,
  slots, layers: ['video footage', 'presenter footage', 'overlay.png'],
  video_fit: 'contain; record at slot aspect ratio to avoid bars',
  presenter_fit: 'cover; adjust crop to keep face in frame',
  preview_only_labels: true,
}, null, 2) + '\n');

// Validate actual exported transparency, dimensions, and both usable apertures.
const { data, info } = await sharp(path.join(directory, 'overlay.png')).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
assert.equal(info.width, width);
assert.equal(info.height, height);
const alphaAt = (x, y) => data[(y * width + x) * 4 + 3];
assert.equal(alphaAt(0, 0), 255);
assert.equal(alphaAt(2098, 720), 255);
assert.equal(slots.video.width / slots.video.height, 16 / 9);
assert.equal(slots.presenter.width / slots.presenter.height, 9 / 16);
assert.equal(slots.video.y + slots.video.height / 2, slots.presenter.y + slots.presenter.height / 2);
// The pastel field reaches every edge; no saturated outer border remains.
for (const [x, y] of [[0, 0], [width - 1, 0], [0, height - 1], [width - 1, height - 1]]) {
  const offset = (y * width + x) * 4;
  assert.ok(data[offset] > 190 && data[offset + 1] > 190 && data[offset + 2] > 190);
  assert.equal(alphaAt(x, y), 255);
}
for (const slot of Object.values(slots)) {
  assert.equal(alphaAt(slot.x + Math.floor(slot.width / 2), slot.y + Math.floor(slot.height / 2)), 0);
  assert.equal(alphaAt(slot.x + 1, slot.y + 1), 255);
}
console.log('Verified 2560 x 1440 assets, transparent video/presenter openings, and rounded corners.');
