# Frontend layout and navigation

Module 5 introduced presentation and navigation using the installed Next.js App Router, React, TypeScript and Tailwind stack. Module 6 extends that shell with [jobs listing/details](jobs.md), module 7 adds [candidate pools/profiles](candidates.md), and module 8 adds [temporary PDF text review](resumes.md). No frontend dependencies were added; matching and screening remain pending.

## Routes and shared shell

| Route | Behavior |
| --- | --- |
| `/` | Overview, planned workflow and explicit feature availability |
| `/guide` | Static explanation of the planned workflow and evidence/privacy principles |
| `/jobs` | Synthetic job catalog from FastAPI, with loading/empty/error states |
| `/jobs/<id>` | Requirements and screening focus, with safe missing/unavailable states |
| `/jobs/<id>/candidates` | Alphabetical synthetic candidate pool scoped to the job |
| `/jobs/<id>/candidates/<candidate_id>` | Profile, source evidence and exact excerpt highlighting |
| Unmatched URL | HTTP 404 with the same shell and a link back to the overview |

`src/components/app-shell.tsx` owns the sidebar, header, main landmark and footer. The sidebar becomes an always-visible horizontal navigation area below 1024 CSS pixels; no menu toggle or hidden focus targets are needed. Cards stack on smaller screens. System fonts and local inline SVG icons require no external assets.

`src/components/navigation.tsx` reads `usePathname` and sets `aria-current="page"` on the active navigation link; Jobs also stays active on job detail routes. Overview/guide and the shell remain server components; job data views use client components for direct FastAPI requests. Normal Next.js links support client navigation, direct URLs, reloads and browser history. Mobile links can wrap without hiding controls. No future feature routes or nonfunctional controls are present.

The first keyboard stop is a visible-on-focus skip link to the focusable main landmark. Interactive links have a three-pixel focus outline, with a color checked for at least 3:1 contrast against the shell's light and dark surfaces. Navigation targets are at least 48 CSS pixels high. Each page has one main landmark and one level-one heading; icons and decorative shapes are hidden from assistive technology. Reduced-motion preferences disable transitions.

## Verification and repeatable browser checks

Use the existing `talent-insight` Conda environment and the commands in [local development](local-development.md). Run `npm run lint`, `npm run typecheck`, `npm run build`, then serve that build with `npm start`. Keep the server on loopback.

Module 5 verification on 2026-10-24:

- ESLint, route generation/TypeScript and the Webpack production build passed.
- Real-browser checks of the production build passed: overview/guide links, call to action, return link, keyboard activation, exact active-page labels, direct guide reload and browser back/forward navigation.
- Tab revealed the skip link with a visible outline; Enter moved focus to `main-content`. Main/heading counts were checked through the rendered DOM.
- Both pages had `scrollWidth === innerWidth` at 320, 375, 768, 1024 and 1280 CSS pixels. Desktop and mobile screenshots were inspected for readable layout and reachable navigation.
- An unmatched URL returned HTTP 404, showed recovery UI without a falsely active navigation link, and its return link reached the overview. Overview, guide and 404 have distinct page titles.
- Browser warning/error logs were empty in the checked session.
- Unchanged backend regression suite: 63 passed, three opt-in Neon checks skipped. No external database/provider checks, migrations, seeds or deployments ran in module 5.

These are focused manual browser/DOM checks, not an automated browser test suite, screen-reader audit or accessibility conformance claim. Other browser engines, hosted deployment and live recruiting workflows remain unverified. Add feature-specific automated coverage when jobs and candidate interactions are implemented in their approved modules.

## Next review gate

Modules 5–7 are approved. Module 8 is complete and awaiting review; see [PDF extraction](resumes.md) and `PROJECT_CONTEXT.md` for verification and the next review gate.
