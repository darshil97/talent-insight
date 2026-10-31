# Talent Insight UI options

Open `index.html` in a browser, then choose a concept. Each concept is a standalone HTML page with shared CSS and JavaScript. No package installation or application server is needed.

1. **Minimal / Paper** — editorial, compact, quiet.
2. **Modern / Studio** — familiar SaaS workspace with clear accents.
3. **Futuristic / Signal** — dark analytics interface with luminous focus.
4. **Sci-fi / Mission** — command-console framing and warm signal color.

Each option includes Overview, Jobs, How it works, job details, and a Candidates tab. The job and candidate data in `demo-data.js` is a static snapshot of the repository's synthetic fixtures. Experience years are shown only where an existing source claim states a duration; these are unverified source claims. Match scores are pending because no cached assessment data exists yet.

Selecting a PDF adds a highlighted **temporary preview row** using only its filename. The prototype does not read the file or call the backend. Call buttons show a preview notice and do not start audio capture or place calls. The row clears on navigation or refresh. These files do not alter the main application.

After a design is selected, the next implementation module should move the temporary upload into the job-scoped Candidates tab and present typed assessment results in the table. A later, separately reviewed backend module can precompute and store validated assessments for the synthetic demo candidates, with a repeatable refresh command. Uploaded candidates and their reports should remain temporary.

## Screening report preview (module 14)

`screening-report.html` is a standalone review page for the module 14 report, so its layout can be reviewed without running a screening:
- **Live sample:** a real `openai.gpt-oss-120b-1:0` report, generated on 2026-10-31, for a synthetic text screening of demo candidate Avery (Senior Data Scientist).
- **Derived states:** ended early, mock mode, preparing and error, all built from the sample.
- **Phone width:** a toggle shows the page at 375 px.

Markup mirrors `frontend/src/components/screening-report.tsx`, and the CSS is copied from `frontend/src/app/globals.css` at generation time. It is a snapshot, so it does not update itself when the component changes. The page calls no backend. Open it through any static server (for example `python3 -m http.server --directory ui-options`); the in-app browser blocks `file:` URLs.

The page now mirrors the recruiter-first component that shipped on 2026-10-31. The live sample gained the server's `resume_status` and `next_step_reasons`, computed offline from the server's own code, so no new model call was made.
