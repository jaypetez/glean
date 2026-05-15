// Generates raster brand assets from SVG sources in /assets.
// Run with: node ui/scripts/generate-brand-png.mjs
// Outputs to: ui/public/

import sharp from "sharp";
import { mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS = resolve(__dirname, "../../assets");
const PUBLIC = resolve(__dirname, "../public");

mkdirSync(PUBLIC, { recursive: true });

async function shot(svgPath, outName, size, opts = {}) {
  const out = resolve(PUBLIC, outName);
  const pipeline = sharp(svgPath, { density: 384 }).resize(size, size, {
    fit: "contain",
    background: opts.background ?? { r: 0, g: 0, b: 0, alpha: 0 },
  });
  await pipeline.png().toFile(out);
  console.log(`✓ ${outName} (${size}x${size})`);
}

async function maskable(svgPath, outName, size) {
  // Maskable icons need a 20% safe-area inset on all sides.
  const out = resolve(PUBLIC, outName);
  const inner = Math.floor(size * 0.6);
  const pad = Math.floor((size - inner) / 2);
  const mark = await sharp(svgPath, { density: 384 })
    .resize(inner, inner, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer();
  await sharp({
    create: {
      width: size,
      height: size,
      channels: 4,
      background: { r: 14, g: 23, b: 48, alpha: 1 },
    },
  })
    .composite([{ input: mark, top: pad, left: pad }])
    .png()
    .toFile(out);
  console.log(`✓ ${outName} (maskable, ${size}x${size})`);
}

async function ogCard() {
  // 1200x630 Open Graph card with vertical logo + tagline on dark gradient.
  const out = resolve(PUBLIC, "og-card.png");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
    <defs>
      <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#070a14"/>
        <stop offset="100%" stop-color="#0e1730"/>
      </linearGradient>
    </defs>
    <rect width="1200" height="630" fill="url(#bg)"/>
    <g transform="translate(450 140) scale(4)">
      <path d="M 32 10 A 22 22 0 1 0 54 32" fill="none" stroke="#22d3ee" stroke-width="6" stroke-linecap="round"/>
      <path d="M 54 32 L 40 32" fill="none" stroke="#22d3ee" stroke-width="6" stroke-linecap="round"/>
      <circle cx="28" cy="28" r="4" fill="#22d3ee"/>
    </g>
    <text x="600" y="490" text-anchor="middle"
      font-family="Inter, system-ui, sans-serif" font-size="72" font-weight="600"
      letter-spacing="-0.02em" fill="#f1f5f9">glean</text>
    <text x="600" y="550" text-anchor="middle"
      font-family="Inter, system-ui, sans-serif" font-size="22" font-weight="400"
      fill="#94a3b8">Self-hosted agent that gleans signal from RSS, scraping, and search</text>
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(out);
  console.log("✓ og-card.png (1200x630)");
}

async function appleTouchIcon() {
  // 180x180 opaque (iOS strips alpha).
  const out = resolve(PUBLIC, "apple-touch-icon.png");
  const svgPath = resolve(ASSETS, "glean-mark.svg");
  const inner = await sharp(svgPath, { density: 384 })
    .resize(140, 140, { fit: "contain" })
    .png()
    .toBuffer();
  await sharp({
    create: {
      width: 180,
      height: 180,
      channels: 4,
      background: { r: 14, g: 23, b: 48, alpha: 1 },
    },
  })
    .composite([{ input: inner, top: 20, left: 20 }])
    .png()
    .toFile(out);
  console.log("✓ apple-touch-icon.png (180x180)");
}

const favicon = resolve(ASSETS, "glean-favicon.svg");
const mark = resolve(ASSETS, "glean-mark.svg");

await shot(favicon, "favicon-16.png", 16);
await shot(favicon, "favicon-32.png", 32);
await shot(favicon, "icon-192.png", 192);
await shot(favicon, "icon-512.png", 512);
await maskable(mark, "icon-maskable-192.png", 192);
await maskable(mark, "icon-maskable-512.png", 512);
await appleTouchIcon();
await ogCard();

console.log("\nAll brand PNGs generated.");
