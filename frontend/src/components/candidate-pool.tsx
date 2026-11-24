"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { AssessmentResult } from "@/components/assessment-result";
import { PhoneIcon } from "@/components/phone-icon";
import { ScreeningPanel } from "@/components/screening-panel";
import { AvailabilityFields, completeAvailability } from "@/components/availability-fields";
import { CatalogLoading, CatalogNotFound, CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { JobTabs } from "@/components/job-tabs";
import { TurnstileWidget } from "@/components/turnstile-widget";
import { assessUpload, AssessmentError, type Assessment } from "@/lib/assessments";
import { AvailabilityError, availabilityLabel, notProvided, requestAvailability, type Availability, type AvailabilityInput } from "@/lib/availability";
import { sortForReview } from "@/lib/candidate-order";
import { decodeCandidatePool, decodeCandidateProfile, type CandidateTableSummary } from "@/lib/candidates";
import { fetchCatalog, type JobDetail } from "@/lib/catalog";
import { prefetchCatalog } from "@/lib/catalog-cache";
import { confidenceLabels, type Confidence } from "@/lib/estimate";
import { decodeResumeLimits, ResumeError, type ResumeLimits } from "@/lib/resumes";
import type { ScreeningCandidate } from "@/lib/screenings";

// Must match RESUME_ACTION in backend/app/voice/turnstile.py.
const BOT_CHECK_ACTION = "resume_assess";

type DemoRow = { kind: "demo"; name: string; rank: number | null; candidate: CandidateTableSummary };
type UploadRow = {
  kind: "upload"; name: string; title: string; rank: number | null; filename: string; assessment: Assessment;
  availabilityInput: AvailabilityInput; availability: Availability | null;
};
type Row = DemoRow | UploadRow;
type ScreeningTarget = { key: string; name: string; candidate: ScreeningCandidate | null };

const rowLabel = (row: Row) => row.kind === "demo" ? row.name : row.name.trim() || "Uploaded candidate";

function Score({ estimate, confidence, available }: { estimate: number | null; confidence: Confidence | null; available: boolean }) {
  if (!available) return <span className="mission-muted">Pending snapshot</span>;
  if (estimate === null || confidence === null) return <span className="mission-muted">Unavailable</span>;
  return <><strong className="mission-score">{estimate.toFixed(1)} <small>/ 100</small></strong><small className={`mission-confidence mission-confidence-${confidence}`}>{confidenceLabels[confidence]} confidence</small></>;
}

function CandidateWorkspace({ job, candidates }: { job: JobDetail; candidates: CandidateTableSummary[] }) {
  const [limits, setLimits] = useState<ResumeLimits | null>(null);
  const [limitsAttempt, setLimitsAttempt] = useState(0);
  const [upload, setUpload] = useState<UploadRow | null>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<AvailabilityInput>(notProvided);
  const [processing, setProcessing] = useState(false);
  // Turnstile tokens work once; a new widget key mints a fresh one after every attempt.
  const [botToken, setBotToken] = useState<string | null>(null);
  const [botAttempt, setBotAttempt] = useState(0);
  const [error, setError] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const [screening, setScreening] = useState<ScreeningTarget | null>(null);
  const [screeningLive, setScreeningLive] = useState(false);
  const closeScreening = useCallback(() => setScreening(null), []);
  const request = useRef<AbortController | null>(null);
  const availabilityRequest = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const details = useRef<HTMLElement>(null);
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchCatalog("/resumes/limits", decodeResumeLimits, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setLimits(value); })
      .catch(() => { if (!controller.signal.aborted) setError("Upload limits could not be loaded. Try again."); });
    return () => controller.abort();
  }, [limitsAttempt]);

  useEffect(() => {
    function discard() {
      request.current?.abort(); availabilityRequest.current?.abort();
      setUpload(null); setProcessing(false); setShowDetails(false); setError(""); setAdding(false); setDraft(notProvided); setScreening(null);
      if (input.current) input.current.value = "";
    }
    function restored(event: PageTransitionEvent) { if (event.persisted) discard(); }
    window.addEventListener("pagehide", discard);
    window.addEventListener("pageshow", restored);
    return () => { request.current?.abort(); availabilityRequest.current?.abort(); window.removeEventListener("pagehide", discard); window.removeEventListener("pageshow", restored); };
  }, []);

  useEffect(() => { if (showDetails) details.current?.focus(); }, [showDetails]);
  useEffect(() => { if (adding) panel.current?.focus(); }, [adding]);

  function clear() {
    request.current?.abort(); availabilityRequest.current?.abort();
    setUpload(null); setProcessing(false); setShowDetails(false); setError(""); setAdding(false); setDraft(notProvided);
    setBotToken(null); setBotAttempt((value) => value + 1);
    setScreening((current) => current?.key === "upload" ? null : current);
    if (input.current) input.current.value = "";
  }

  /** Opens the consent step below the table; the backend allows one screening at a time. */
  function screen(row: Row) {
    setScreening(row.kind === "demo"
      ? { key: row.candidate.id, name: row.name, candidate: { kind: "demo", candidate_id: row.candidate.id } }
      : { key: "upload", name: rowLabel(row), candidate: row.assessment.screening_context ? { kind: "upload", context: row.assessment.screening_context } : null });
  }

  /** Only the cheap availability calculation runs again; the AI assessment is never repeated. */
  async function rank(row: UploadRow, details: AvailabilityInput): Promise<UploadRow> {
    availabilityRequest.current?.abort();
    const controller = new AbortController();
    availabilityRequest.current = controller;
    const value = completeAvailability(details);
    try {
      const result = await requestAvailability(value, row.assessment.scoring.estimate, controller.signal);
      return { ...row, availabilityInput: value, availability: result.availability, rank: result.ranking_score };
    } catch (failure) {
      if (controller.signal.aborted) throw failure;
      if (failure instanceof AvailabilityError) setError(failure.message);
      return { ...row, availabilityInput: value, availability: null, rank: row.assessment.scoring.estimate };
    }
  }

  async function updateAvailability() {
    if (!upload) return;
    setError("");
    try { setUpload(await rank(upload, upload.availabilityInput)); } catch { /* superseded or cleared */ }
  }

  async function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !limits) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const token = botToken;
    setBotToken(null); setBotAttempt((value) => value + 1);
    setUpload(null); setShowDetails(false); setError(""); setProcessing(true);
    try {
      const assessment = await assessUpload(file, limits, job, controller.signal, token);
      const identity = assessment.structured.identity;
      const row: UploadRow = {
        kind: "upload", name: identity?.name?.value ?? "", title: identity?.current_title?.value ?? "",
        rank: assessment.scoring.estimate, filename: file.name, assessment, availabilityInput: draft, availability: null,
      };
      const ranked = await rank(row, draft);
      if (!controller.signal.aborted) setUpload(ranked);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof ResumeError || failure instanceof AssessmentError ? failure.message : "Assessment could not be completed. Check the connection and try again.");
    } finally {
      if (!controller.signal.aborted) setProcessing(false);
      if (input.current) input.current.value = "";
    }
  }

  const rows: Row[] = sortForReview<Row>([
    ...candidates.map((candidate): DemoRow => ({ kind: "demo", name: candidate.display_name, rank: candidate.ranking_score, candidate })),
    // An unnamed upload sorts under its display label, not as an empty name.
    ...(upload ? [{ ...upload, name: upload.name.trim() || "Uploaded candidate" }] : []),
  ]);
  function warmProfile(candidateId: string) {
    prefetchCatalog(`/jobs/${job.id}/candidates/${candidateId}`, (value) => decodeCandidateProfile(value, job.id, candidateId));
  }
  const identity = upload?.assessment.structured.identity;

  return <>
    <section className="mission-role-heading"><div><p className="mission-kicker">SYNTHETIC DEMO ROLE / {job.client}</p><h1>{job.title}<span>.</span></h1><p>{job.description}</p></div><div className="mission-role-stamp"><small>ROLE FILE</small><strong>{job.id.replace("demo_", "").toUpperCase()}</strong><small>{candidates.length} DEMO PROFILES</small></div></section>
    <JobTabs jobId={job.id} active="candidates" count={rows.length} />
    <section className="mission-pool-heading"><div><p className="mission-kicker">CANDIDATE POOL / {candidates.length} SYNTHETIC PROFILES</p><h2>People for this role<span>.</span></h2><p>Candidates sort by match estimate plus a small availability bonus for a shorter time to join. Unverified requirements count at half credit in the estimate; the confidence label shows how much is still unverified.</p></div><button type="button" className="mission-button mission-upload" disabled={!limits || processing} aria-expanded={adding || upload !== null} aria-controls="add-candidate-panel" onClick={() => setAdding(true)}>＋ Add resume PDF</button><input ref={input} id="candidate-resume" className="sr-only" tabIndex={-1} type="file" accept=".pdf,application/pdf" disabled={!limits || processing} aria-describedby="candidate-upload-help" onChange={selectFile} /></section>
    {(adding || upload) && <section id="add-candidate-panel" ref={panel} tabIndex={-1} aria-labelledby="add-candidate-heading" className="mission-add-panel">
      <h3 id="add-candidate-heading">{upload ? "Uploaded candidate details" : "Add a candidate"}</h3>
      {upload && <div className="mission-identity">
        <label htmlFor="upload-name">Name<input id="upload-name" value={upload.name} maxLength={120} onChange={(event) => setUpload({ ...upload, name: event.target.value })} /></label>
        <label htmlFor="upload-title">Current position<input id="upload-title" value={upload.title} maxLength={160} onChange={(event) => setUpload({ ...upload, title: event.target.value })} /></label>
        <p className="mission-help">{identity?.name || identity?.current_title ? "Prefilled from text found in the resume. Edit if needed; these fields are never used for scoring." : "Name and position were not found in the resume. Add them if you know them; they are never used for scoring."}</p>
      </div>}
      <AvailabilityFields id="upload-availability" value={upload ? upload.availabilityInput : draft} onChange={(value) => upload ? setUpload({ ...upload, availabilityInput: value }) : setDraft(value)} />
      {upload ? <button type="button" className="mission-outline-button" onClick={updateAvailability}>Update availability</button>
        : <>{limits?.bot_check_site_key && !processing && <TurnstileWidget key={botAttempt} siteKey={limits.bot_check_site_key} action={BOT_CHECK_ACTION} onToken={setBotToken} help="Cloudflare checks that you're a person before the resume is assessed." />}<button type="button" className="mission-button" disabled={!limits || processing || (!!limits.bot_check_site_key && !botToken)} onClick={() => input.current?.click()}>Choose PDF</button> <button type="button" className="mission-outline-button" disabled={processing} onClick={clear}>Cancel</button></>}
    </section>}
    <p id="candidate-upload-help" className="mission-help">Choose a text-based PDF you have permission to process. Selection immediately sends it to the backend’s configured AI provider when Bedrock mode is active. Results need human review and clear on refresh. Scanned and password-protected PDFs are unsupported.</p>
    <p className="mission-upload-state" role="status">{processing ? <>Assessing the selected PDF… <button type="button" onClick={clear}>Cancel</button></> : upload ? <>New candidate added for this session. <button type="button" onClick={clear}>Clear upload</button></> : limits ? `PDF limit: ${(limits.max_bytes / (1024 * 1024)).toFixed(1)} MiB · ${limits.max_pages} pages` : <>Loading PDF limits… <button type="button" onClick={() => { setError(""); setLimitsAttempt((value) => value + 1); }}>Retry</button></>}</p>
    {error && <p role="alert" className="mission-error">{error}</p>}
    <div className="mission-table-panel"><div className="mission-table-bar"><div><span>▦</span><strong>Candidate overview</strong><small>{rows.length}</small></div><small>JOB-SPECIFIC VIEW</small></div><div className="mission-table-scroll"><table className="mission-table"><thead><tr><th scope="col">Candidate name</th><th scope="col">Title</th><th scope="col">Experience</th><th scope="col">Match estimate</th><th scope="col">Availability</th><th scope="col">Source</th><th scope="col">Screening</th><th scope="col">Details</th></tr></thead><tbody>
      {rows.map((row) => <tr key={row.kind === "demo" ? row.candidate.id : "uploaded"} className={row.kind === "upload" ? "mission-new-row" : ""}>
        <td><div className="mission-person"><span className="mission-avatar">{row.kind === "demo" ? row.name.split(" ").map((part) => part[0]).join("") : "↑"}</span><div>{row.kind === "demo" ? <Link onMouseEnter={() => warmProfile(row.candidate.id)} onFocus={() => warmProfile(row.candidate.id)} href={`/jobs/${job.id}/candidates/${row.candidate.id}`}>{row.name}</Link> : <button type="button" onClick={() => setShowDetails(true)}>{row.name.trim() || "Uploaded candidate"} <b>JUST ADDED</b></button>}<small>{row.kind === "demo" ? "Synthetic demo candidate" : row.filename}</small></div></div></td>
        <td>{row.kind === "demo" ? row.candidate.headline : row.title.trim() || <span className="mission-muted">Not provided</span>}</td>
        <td>{row.kind === "demo" && row.candidate.stated_experience ? <>{row.candidate.stated_experience}<small className="mission-stated">stated</small></> : <span className="mission-muted">Unknown</span>}</td>
        <td><Score estimate={row.kind === "upload" ? row.assessment.scoring.estimate : row.candidate.match_estimate} confidence={row.kind === "upload" ? row.assessment.scoring.confidence : row.candidate.confidence} available={row.kind === "upload" || row.candidate.snapshot_available} /></td>
        <td><span className={(row.kind === "demo" ? row.candidate.availability.status : row.availability?.status) ? "" : "mission-muted"}>{availabilityLabel(row.kind === "demo" ? row.candidate.availability : row.availability)}</span></td>
        <td><span className="mission-tag">{row.kind === "demo" ? "Demo" : "Temporary"}</span></td>
        <td><button type="button" className="mission-outline-button mission-start-button" disabled={screeningLive || (row.kind === "upload" && !row.assessment.screening_context)} aria-label={`Start screening for ${rowLabel(row)}`} title={screeningLive ? "A screening is in progress" : row.kind === "upload" && !row.assessment.screening_context ? "Screening is not configured on the backend" : undefined} onClick={() => screen(row)}><PhoneIcon />Start</button></td>
        <td>{row.kind === "demo" ? <Link className="mission-outline-button" aria-label={`View details for ${row.name}`} onMouseEnter={() => warmProfile(row.candidate.id)} onFocus={() => warmProfile(row.candidate.id)} href={`/jobs/${job.id}/candidates/${row.candidate.id}`}>View ↗</Link> : <button type="button" className="mission-outline-button" aria-label={`View details for ${rowLabel(row)}`} onClick={() => setShowDetails(true)}>View ↗</button>}</td>
      </tr>)}
    </tbody></table></div><div className="mission-table-foot"><span>Demo scores come from the last validated snapshot; availability is self-reported.</span><span>Uploaded results clear on refresh or navigation.</span></div></div>
    {screening && <ScreeningPanel key={`screening/${job.id}/${screening.key}`} jobId={job.id} jobTitle={job.title} candidate={screening.candidate} candidateName={screening.name} autoOpen onLiveChange={setScreeningLive} onClose={closeScreening} unavailableReason="Screening is not configured on the backend, so this assessment has no screening context." />}
    {upload && showDetails && <section ref={details} tabIndex={-1} aria-labelledby="uploaded-candidate-heading" className="mission-detail-panel"><div className="mission-detail-top"><div><p className="mission-kicker">TEMPORARY CANDIDATE / SOURCE REVIEW</p><h2 id="uploaded-candidate-heading">{upload.name.trim() || "Uploaded candidate"}</h2><p>{upload.title.trim() || "Position not provided"} · {availabilityLabel(upload.availability)}. Review the source evidence before using this assessment.</p></div><div className="mission-detail-actions"><button type="button" className="mission-outline-button" disabled={screeningLive || !upload.assessment.screening_context} onClick={() => screen(upload)}><PhoneIcon />Start screening</button><button type="button" className="mission-outline-button" onClick={() => setShowDetails(false)}>Close details</button></div></div><AssessmentResult assessment={upload.assessment} job={job} /></section>}
    <p className="mission-review-note">Assessments and optional AI screenings support human review. People make the final decision.</p>
  </>;
}

export function CandidatePoolView({ jobId }: { jobId: string }) {
  const decode = useCallback((value: unknown) => decodeCandidatePool(value, jobId), [jobId]);
  const pool = useCatalog(`/jobs/${encodeURIComponent(jobId)}/candidates`, decode);
  if (pool.resource.status === "loading") return <CatalogLoading label="Loading the candidate pool…" />;
  if (pool.resource.status === "error") return pool.resource.notFound ? <CatalogNotFound /> : <CatalogUnavailable retry={pool.retry} subject="candidate pool" />;
  return <CandidateWorkspace key={jobId} job={pool.resource.data.job} candidates={pool.resource.data.candidates} />;
}
