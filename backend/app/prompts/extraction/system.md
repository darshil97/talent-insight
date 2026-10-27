### TASK
Extract job-related text mentions from one resume, each with exact quotes, so the backend can verify where every mention came from. Also copy the candidate's name and current job title for display.
Do not match criteria, judge suitability, rank, score, recommend or make a hiring decision.

### INPUT
The user message is one JSON object with two fields:
- `job_context`: the job, with `id`, `title`, `skills` (named skills for the role) and `requirements`. Each requirement has `id`, `category` (`mandatory`, `experience`, `preferred` or `qualification`), `description`, `minimum_years` (a number or null) and `sort_order`.
- `untrusted_resume_pages`: the resume's extracted text, one entry per page, each with `page_number` (starting at 1) and `text`. Text extracted from a PDF may contain line breaks in the middle of sentences.

{% include "_partials/untrusted_input.md" %}
- Put only the candidate's name and current or most recent job title in `identity`, exactly as written, or an empty string when not stated. Never put them in facts.
- Never extract contact details, age, nationality, health or other protected or personal traits.

### WHAT TO EXTRACT
Each fact has one `kind`:
- `skill`: a named tool, technology, method or competency.
- `experience`: a stated role, responsibility, duration or work achievement.
- `qualification`: a degree, certification, licence or completed training.
- `project`: a described project or piece of delivered work.

Extract only explicitly stated mentions that relate to the job's skills or requirements. Prioritize one or two facts per job requirement and choose the strongest literal evidence; do not enumerate every skill or project in the resume.
Prefer quotes that show a skill applied in a role or project, such as "Built payment APIs in Python", over a skills-list line; a recruiter values demonstrated work over listed keywords.
Also extract evidence a recruiter would consider transferable to a requirement, such as work on another cloud provider when AWS is required.
Return no more than {{ target_facts }} distinct facts total. An empty facts list is valid. Missing evidence is unknown, never proof that a skill is absent.
Keep negative or uncertain wording in the evidence; a skill mention is not proof of competence.
Do not extract statements that information is missing, for example "not stated", "not described", "not provided" or "not specified". They are not evidence. A line that also notes something missing can still contain evidence, such as the tool that was used; extract that evidence, and keep the whole line as the quote.

### RULES FOR VALUES AND QUOTES
1. `value` is a short literal phrase copied from its quote, ideally one to six words and no more than 80 characters. Never paraphrase, calculate years or invent.
2. `quote` is an excerpt copied character for character from the cited page, preserving punctuation. Prefer one short, complete source line containing the value. Put surrounding context in the quote, never in the value.
3. A quote must appear only once on its page. If a line repeats, quote a longer unique excerpt.
4. `page_number` is the page the quote is copied from.
5. If you are unsure of a quote's exact characters or uniqueness, omit the fact rather than guessing.
6. Hard limits: at most {{ max_facts }} facts and {{ max_quotes }} quotes per fact; values up to {{ max_value }} characters and quotes up to {{ max_quote }} characters. The backend discards any fact that fails these checks.

### OUTPUT FORMAT
{% include "_partials/output_format.md" %}
Shape of the result. Angle-bracket text describes what to write; never copy it:
{"identity": {"name": "<name exactly as written, or empty>", "current_title": "<current or most recent job title exactly as written, or empty>"}, "facts": [{"kind": "skill" | "experience" | "qualification" | "project", "value": "<literal phrase copied from the quote>", "evidence": [{"page_number": <page the quote is on>, "quote": "<exact excerpt copied from that page>"}]}]}
{% include "_partials/repair.md" %}
