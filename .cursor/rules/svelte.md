---
description: Svelte 5 + Tailwind v4 conventions for glean UI
globs: ["ui/src/**/*.svelte", "ui/src/**/*.ts"]
---

# UI conventions

- Svelte 5 runes (`$state`, `$derived`, `$effect`) — not legacy reactive declarations
- API calls go through `ui/src/lib/api.ts` (uses `apiFetch` / `apiJson` helpers)
- Auth via `X-Glean-Api-Key` header (auto-set by `apiFetch`); never construct your own fetch
- Design tokens in `ui/src/app.css` — use Tailwind utility classes that reference them (`text-primary`, `bg-surface`, etc.); never hardcode hex
- No emoji as icons — use `phosphor-svelte` Phosphor Icons
- Solid surfaces only — no glassmorphism, no AI-generated gradients
- All inputs need visible labels (a11y); use semantic HTML over ARIA where possible
- After editing, run: `cd ui && npm run build` (catches type errors via tsc)
