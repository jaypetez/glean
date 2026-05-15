# Brand assets

Logo files for glean. All SVG, scalable to any size.

| File | Use case |
|---|---|
| `glean-mark.svg` | Icon-only, cyan on transparent. App icons, buttons, anywhere the wordmark is unnecessary. |
| `glean-mark-mono.svg` | Same mark using `currentColor`. Inline embeds where the icon should follow theme color. |
| `glean-logo.svg` | Mark + dark wordmark. README hero, light docs, light social cards. |
| `glean-logo-dark.svg` | Mark + light wordmark. Dark UI shells, dark social cards. |
| `glean-logo-vertical.svg` | Vertical lockup (mark above wordmark). Square thumbnails, OG images. |
| `glean-logo-mono.svg` | Single-color full lockup using `currentColor`. Inline embeds. |
| `glean-favicon.svg` | Mark on rounded dark surface. Browser tab favicon. |

## Concept

The mark is an open "G" with a single dot inside the bowl — a literal interpretation of *gleaning*: capturing one piece of valuable signal from scattered noise. The G's tongue (the small bar at the right) is the distinguishing feature that keeps it readable as a G even at 16×16.

## Color

- Primary accent: **cyan `#22d3ee`** (Tailwind cyan-400)
- Dark surface: `#0e1730`
- Light surface: `#ffffff`
- Wordmark on light: `#0e1730`
- Wordmark on dark: `#f1f5f9`

## Typography

The wordmark uses **Inter** (semibold, tracking `-0.02em`). Falls back gracefully to `system-ui` and platform sans. For absolute portability across systems without Inter, run the SVG through `npx svgo` with `convertText` enabled to outline the glyphs.

## Don't

- Don't recolor the dot independently of the arc (they're one mark)
- Don't add gradients or drop shadows
- Don't surround with a circular badge — the geometry is already self-contained
- Don't render the wordmark in italic; the typeface only works upright

## Other assets

- `glean-hero.svg` — architecture diagram (pipeline flow), used as the README banner. This is not a logo.
- `screenshots/` — UI screenshots used in the README and docs.

## Regenerating PNG variants

Some places (PWA manifest icons, Open Graph cards, Apple touch icons) need raster PNGs. They're generated from the SVG sources via:

```bash
cd ui
node scripts/generate-brand-png.mjs
```

Generated artifacts (committed to `ui/public/`):
- `favicon-16.png`, `favicon-32.png` — old-browser fallbacks
- `icon-192.png`, `icon-512.png` — PWA manifest icons (any purpose)
- `icon-maskable-192.png`, `icon-maskable-512.png` — PWA maskable icons (with safe-area padding)
- `apple-touch-icon.png` (180×180, opaque)
- `og-card.png` (1200×630) — Open Graph / Twitter social preview

Re-run after editing any SVG in this directory.
