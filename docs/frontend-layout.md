# Frontend layout and navigation

Next.js App Router, React, TypeScript and Tailwind in `frontend/src`. Pages are server components; data views are client components that call FastAPI from the browser. Feature behaviour is in [jobs](jobs.md), [candidates](candidates.md), [assessment UI](assessment-ui.md) and [voice sessions](voice-sessions.md).

## Routes

| Route | Content |
| --- | --- |
| `/` | Overview, workflow, "What it checks" and the default requirement-credit scale |
| `/guide` | How it works and review principles |
| `/jobs` | Job catalog, with loading, empty and error states |
| `/jobs/<jobId>` | Details tab: requirements, screening criteria, questions |
| `/jobs/<jobId>/candidates` | Candidates tab: ranked pool, PDF upload, screening |
| `/jobs/<jobId>/candidates/<candidateId>` | Profile and resume with evidence excerpt highlighting |
| Anything else | 404 in the same shell, linking to the overview |

- `/` and `/guide` need no backend; `/jobs` routes do.
- Malformed IDs show a not-found state without an API call.

## Shell

- `app-shell.tsx` renders the skip link, sidebar, top bar, `main#main-content` and footer for every page.
- `navigation.tsx` sets `aria-current="page"`; Jobs stays active on `/jobs/...` and shows the job count there. `job-tabs.tsx` switches a job's Details and Candidates tabs and prefetches on hover or focus.
- At 800 CSS pixels and below, the sidebar becomes a top block with a horizontally scrollable navigation row.
- Dark theme, system fonts, local glyphs and SVG icons. The only external script is Cloudflare Turnstile, loaded in the screening consent step when the backend enables it.

## Data loading

- The API origin is `NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:8000`), validated as a bare origin, HTTPS unless loopback, and built into the bundle. See [configuration](configuration.md).
- Catalog GETs are uncached by the browser, send no credentials, refuse redirects and time out after 20 seconds. `lib/catalog-cache.ts` keeps synthetic catalog responses in memory for 60 seconds.
- Upload results live only in component state; refresh or navigation clears them.

## Accessibility

- A skip link is the first Tab stop; interactive elements show a visible focus outline.
- Navigation links, tabs and primary buttons are at least 48 CSS pixels high.
- Decorative glyphs and icons are hidden from assistive technology.
- `prefers-reduced-motion` disables transitions and animations.
- There is no automated browser or screen-reader suite; layout and keyboard behaviour are checked manually.
