/* Standalone visual prototype. No PDF content is read and no network request is made. */
(() => {
  const jobs = window.TALENT_DEMO_DATA;
  const root = document.querySelector("#app");
  const theme = document.documentElement.dataset.theme;
  const names = { minimal: "Minimal / Paper", modern: "Modern / Studio", futuristic: "Futuristic / Signal", scifi: "Sci-fi / Mission" };
  let uploadedName = "";
  let toast = "";

  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const href = (part) => `#${part}`;
  const jobUrl = (job, tab = "details") => href(`jobs/${job.id}/${tab}`);

  function locationState() {
    const parts = decodeURIComponent(location.hash.slice(1)).split("/").filter(Boolean);
    const job = jobs.find((item) => item.id === parts[1]) || jobs.find((item) => item.id === "demo_ds") || jobs[0];
    return { screen: parts[0] || "overview", job, tab: parts[2] === "candidates" ? "candidates" : "details" };
  }

  function shell(content, state) {
    const inJob = state.screen === "jobs";
    return `<a class="skip" href="#main">Skip to content</a>
      <div class="workspace">
        <aside class="sidebar">
          <a class="brand" href="#overview" aria-label="Talent Insight overview"><span class="brand-mark" aria-hidden="true">✳</span><span>talent<span class="brand-light"> insight</span><b>.</b></span></a>
          <p class="side-caption">WORKSPACE / 01</p>
          <nav class="main-nav" aria-label="Main navigation">
            <a class="${state.screen === "overview" ? "active" : ""}" href="#overview"><span>◫</span> Overview</a>
            <a class="${inJob ? "active" : ""}" href="#jobs"><span>▤</span> Jobs <em>04</em></a>
            <a class="${state.screen === "guide" ? "active" : ""}" href="#guide"><span>◇</span> How it works</a>
          </nav>
          <div class="side-bottom"><span class="pulse-dot"></span><div><strong>Design preview</strong><small>Concept ${Object.keys(names).indexOf(theme) + 1} of 4</small></div></div>
        </aside>
        <div class="body-column">
          <header class="topbar"><div class="breadcrumbs">TALENT INSIGHT <span>/</span> ${state.screen === "overview" ? "OVERVIEW" : state.screen === "guide" ? "HOW IT WORKS" : state.screen === "jobs" && !location.hash.includes(state.job.id) ? "JOBS" : escapeHtml(state.job.title.toUpperCase())}</div><a class="switch-concept" href="index.html">View all concepts ↗</a></header>
          <main id="main">${content}</main>
          <footer class="footer"><span>Talent Insight · ${names[theme]}</span><span>Synthetic demo data · People make final hiring decisions</span></footer>
        </div>
      </div>
      <div class="toast ${toast ? "shown" : ""}" role="status">${escapeHtml(toast)}</div>`;
  }

  function overview() {
    return `<section class="intro overview-intro"><div><p class="eyebrow">RECRUITING, WITH CONTEXT</p><h1>A clearer view of every candidate<span class="accent">.</span></h1><p class="lead">Bring job requirements, candidate evidence and thoughtful questions into one place.</p><a class="primary-button" href="#jobs">Explore jobs <span>↗</span></a></div><div class="hero-visual" aria-hidden="true"><div class="hero-orbit orbit-one"></div><div class="hero-orbit orbit-two"></div><div class="hero-center">TI<span>↗</span></div><div class="visual-chip chip-a">EVIDENCE</div><div class="visual-chip chip-b">HUMAN REVIEW</div></div></section>
      <section class="overview-lower"><div class="section-line"><p class="eyebrow">THE WORKFLOW</p><span>01 / 03</span></div><div class="step-grid"><article><span>01</span><h3>Start with a role</h3><p>Review the requirements and the candidates attached to that job.</p></article><article><span>02</span><h3>Compare evidence</h3><p>Use a job-specific assessment as a starting point for human review.</p></article><article><span>03</span><h3>Continue the conversation</h3><p>Follow up on open questions before making a decision.</p></article></div></section>`;
  }

  function jobsPage() {
    return `<section class="page-heading"><div><p class="eyebrow">THE CATALOG / 04 ROLES</p><h1>Explore jobs<span class="accent">.</span></h1><p class="lead">Select a role to review requirements and its candidate pool.</p></div><div class="heading-symbol" aria-hidden="true">04<span>ROLES</span></div></section>
      <div class="job-grid">${jobs.map((job, index) => `<a class="job-card" href="${jobUrl(job)}"><div class="job-card-top"><span class="job-index">0${index + 1} / ROLE</span><span class="arrow-circle">↗</span></div><div><p class="job-client">${escapeHtml(job.client)}</p><h2>${escapeHtml(job.title)}</h2><p class="job-copy">${escapeHtml(job.description)}</p></div><div class="job-card-bottom"><span>${job.candidates.length} synthetic candidates</span><span>View role ↗</span></div></a>`).join("")}</div>`;
  }

  function detailPage(job, tab) {
    const tabs = `<nav class="tabbar" aria-label="Job sections"><a href="${jobUrl(job)}" class="${tab === "details" ? "selected" : ""}" ${tab === "details" ? 'aria-current="page"' : ""}>Job details</a><a href="${jobUrl(job, "candidates")}" class="${tab === "candidates" ? "selected" : ""}" ${tab === "candidates" ? 'aria-current="page"' : ""}>Candidates <span>${job.candidates.length + (uploadedName ? 1 : 0)}</span></a></nav>`;
    return `<a class="back-link" href="#jobs">← All jobs</a><section class="role-hero"><div><p class="eyebrow">SYNTHETIC DEMO ROLE / ${escapeHtml(job.client)}</p><h1>${escapeHtml(job.title)}<span class="accent">.</span></h1><p>${escapeHtml(job.description)}</p></div><div class="role-stamp"><span>ROLE FILE</span><strong>${escapeHtml(job.id.replace("demo_", "").toUpperCase())}</strong><small>${job.candidates.length} demo profiles</small></div></section>${tabs}${tab === "candidates" ? candidatesPage(job) : requirementsPage(job)}`;
  }

  function requirementsPage(job) {
    return `<div class="details-grid"><section class="panel requirements"><div class="panel-head"><p class="eyebrow">ROLE BRIEF</p><span>01 / REQUIREMENTS</span></div><h2>What the role calls for</h2><ul>${job.requirements.map((requirement) => `<li><span class="check-icon">↗</span>${escapeHtml(requirement)}</li>`).join("")}</ul></section><aside class="panel aside-panel"><p class="eyebrow">CANDIDATE WORKFLOW</p><h2>Review the pool in context.</h2><p>Open Candidates to compare job-related evidence and add a temporary resume for this role.</p><a class="primary-button" href="${jobUrl(job, "candidates")}">View candidates <span>↗</span></a><div class="skill-cloud">${job.skills.map((skill) => `<span>${escapeHtml(skill)}</span>`).join("")}</div></aside></div>`;
  }

  function candidatesPage(job) {
    const rows = [...job.candidates].sort((a, b) => a.name.localeCompare(b.name));
    const uploadRow = uploadedName ? `<tr class="uploaded-row"><td><div class="person"><span class="avatar upload-avatar">↑</span><div><strong>New upload <span class="new-badge">JUST ADDED</span></strong><small>${escapeHtml(uploadedName)}</small></div></div></td><td>Extraction pending</td><td>Unknown</td><td><span class="score-pending">Awaiting assessment</span></td><td><span class="status-tag">Temporary</span></td><td><button type="button" class="text-action" data-action="upload-info">Review →</button></td></tr>` : "";
    return `<section class="pool-header"><div><p class="eyebrow">CANDIDATE POOL / ${job.candidates.length} SYNTHETIC PROFILES</p><h2>People for this role<span class="accent">.</span></h2><p>Stated years are source claims, not verified experience. Match scores will appear here after backend assessment and review.</p></div><label class="upload-button" for="resume-file"><span>＋</span> Add resume PDF</label><input id="resume-file" class="visually-hidden" type="file" accept=".pdf,application/pdf" aria-describedby="upload-help"></section>
      <div id="upload-help" class="upload-help">Temporary preview: choosing a PDF highlights a row. This prototype does not read, upload, extract or score the file.</div>
      <div class="table-panel"><div class="table-toolbar"><div><span class="table-icon">▦</span><strong>Candidate overview</strong><span class="count-pill">${job.candidates.length + (uploadedName ? 1 : 0)}</span></div><span class="table-note">JOB-SPECIFIC VIEW</span></div><div class="table-scroll"><table><thead><tr><th>Candidate name</th><th>Title</th><th>Experience years</th><th>Match score</th><th>Source</th><th>Call</th></tr></thead><tbody>${uploadRow}${rows.map((candidate) => `<tr><td><div class="person"><span class="avatar">${escapeHtml(candidate.name.split(" ").map((part) => part[0]).join(""))}</span><div><strong>${escapeHtml(candidate.name)}</strong><small>Synthetic demo candidate</small></div></div></td><td>${escapeHtml(candidate.title)}</td><td>${candidate.experience ? `${escapeHtml(candidate.experience)} <small class="stated">stated</small>` : '<span class="unknown">Unknown</span>'}</td><td><span class="score-pending">Pending snapshot</span></td><td><span class="status-tag">Demo</span></td><td><button type="button" class="call-button" data-action="call" data-name="${escapeHtml(candidate.name)}">Call ↗</button></td></tr>`).join("")}</tbody></table></div><div class="table-foot"><span>Demo scores are intended to be precomputed and stored after the backend workflow is approved.</span><span>Upload results clear on refresh.</span></div></div>
      <div class="pool-bottom"><div><p class="eyebrow">HUMAN REVIEW</p><h3>Scores need their evidence.</h3><p>A future score should open its criterion breakdown, source excerpts and unresolved requirements.</p></div><div class="small-graphic" aria-hidden="true"><span></span><span></span><span></span></div></div>`;
  }

  function guide() {
    return `<section class="page-heading"><div><p class="eyebrow">HOW IT WORKS / 03 STEPS</p><h1>From role to review<span class="accent">.</span></h1><p class="lead">A simple job-specific path, with evidence visible to the person making the final decision.</p></div></section><div class="guide-grid"><article><span>01 / SELECT</span><h2>Choose a job</h2><p>Read its requirements and open the Candidates tab.</p></article><article><span>02 / REVIEW</span><h2>Compare candidates</h2><p>Review synthetic demo profiles and, later, their stored assessments. Add a PDF to request a temporary assessment for the selected job.</p></article><article><span>03 / FOLLOW UP</span><h2>Talk to a person</h2><p>Use a consent-aware call or text path only after the interview module is implemented. Keep the final decision with a human.</p></article></div><a class="primary-button guide-button" href="#jobs">Browse jobs <span>↗</span></a>`;
  }

  function render() {
    const state = locationState();
    let content;
    if (state.screen === "guide") content = guide();
    else if (state.screen === "jobs" && location.hash.includes(state.job.id)) content = detailPage(state.job, state.tab);
    else if (state.screen === "jobs") content = jobsPage();
    else content = overview();
    root.innerHTML = shell(content, state);
  }

  window.addEventListener("hashchange", () => { uploadedName = ""; toast = ""; render(); });
  root.addEventListener("change", (event) => {
    if (event.target.id !== "resume-file") return;
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) { toast = "Choose a PDF file for this preview."; render(); return; }
    uploadedName = file.name;
    toast = "Highlighted temporary row added. No file content was processed.";
    render();
  });
  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    if (button.dataset.action === "call") toast = `Call flow preview for ${button.dataset.name}. No call was placed.`;
    if (button.dataset.action === "upload-info") toast = "Assessment is pending in this design preview. No PDF was processed.";
    render();
  });
  render();
})();
