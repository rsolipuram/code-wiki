# Frontend — code-wiki

Next.js + TypeScript + React frontend.

## Commands

```bash
npm run dev     # Start dev server on port 3000
npm run build   # Production build
```

## UX Design System

**Typography**: IBM Plex Mono (code), Crimson Pro (body), System fonts (UI)

**Color Palette**:
- Sky blue `#0ea5e9` — Parameters, links
- Emerald `#10b981` — Types, success
- Purple `#a855f7` — Return values, keywords
- Amber `#f59e0b` — Highlights, active
- Slate `#64748b` — Secondary text, borders

**CSS Variables** (glassmorphism design system):
- Link color: `var(--secondary)` = `#06B6D4` (cyan)
- Hover: `var(--primary-light)` = `#A78BFA` (light purple)
- Apply ONLY to content pages, NOT navigation/sidebar/buttons

**Interaction Patterns**: Gradient accent bars on hover, border transitions, shadow elevation, vertical lift (2-4px), staggered fade-in sequences.

## Route Structure

- `/` — Landing page
- `/dashboard` — Repository list
- `/submit` — Add repository
- `/[owner]/[name]` — Wiki home (unified 3-column reader)
- `/[owner]/[name]/[slug]` — Wiki section page
- `/[owner]/[name]/progress` — Analysis progress

## Gotchas

- **Mermaid SVG rendering**: `V2Components.tsx` uses `innerHTML` for mermaid SVG — triggers hook warnings but is safe (library-generated, not user HTML). Approve when prompted
- **API error unwrapping**: `api.ts` must unwrap `{"detail": {...}}` from backend error responses
- **UX mocks**: Reference designs in `specs/001-code-wiki/ux/docs-glassmorphism/`
