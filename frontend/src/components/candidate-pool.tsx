"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { AssessmentResult } from "@/components/assessment-result";
import { CatalogLoading, CatalogNotFound, CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { JobTabs } from "@/components/job-tabs";
import { assessUpload, AssessmentError, type Assessment } from "@/lib/assessments";
import { sortByMatchScore } from "@/lib/candidate-order";
import { decodeCandidatePool, type CandidateTableSummary } from "@/lib/candidates";
import { decodeJob, fetchCatalog, type JobDetail } from "@/lib/catalog";
import { decodeResumeLimits, ResumeError, type ResumeLimits } from "@/lib/resumes";

type DemoRow = { kind: "demo"; name: string; score: number | null; candidate: CandidateTableSummary };
type UploadRow = { kind: "upload"; name: string; score: number | null; filename: string; assessment: Assessment };
type Row = DemoRow | UploadRow;

function Score({ score, lower, upper, available }: { score: number | null; lower: number | null; upper: number | null; available: boolean }) {
  if (!available) return <span className="mission-muted">Pending snapshot</span>;
  if (score !== null) return <strong className="mission-score">{score.toFixed(1)} <small>/ 100</small></strong>;
  if (lower !== null && upper !== null) return <span className="mission-muted">{lower.toFixed(1)}–{upper.toFixed(1)} range</span>;
  return <span className="mission-muted">Unavailable</span>;
}

function CandidateWorkspace({ job, candidates }: { job: JobDetail; candidates: CandidateTableSummary[] }) {
  const [limits, setLimits] = useState<ResumeLimits | null>(null);
  const [limitsAttempt, setLimitsAttempt] = useState(0);
  const [upload, setUpload] = useState<UploadRow | null>(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const request = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const details = useRef<HTMLElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchCatalog("/resumes/limits", decodeResumeLimits, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setLimits(value); })
      .catch(() => { if (!controller.signal.aborted) setError("Upload limits could not be loaded. Try again."); });
    return () => controller.abort();
  }, [limitsAttempt]);

  useEffect(() => {
    function discard() {
      request.current?.abort();
      setUpload(null); setProcessing(false); setShowDetails(false); setError("");
      if (input.current) input.current.value = "";
    }
    function restored(event: PageTransitionEvent) { if (event.persisted) discard(); }
    window.addEventListener("pagehide", discard);
    window.addEventListener("pageshow", restored);
    return () => { request.current?.abort(); window.removeEventListener("pagehide", discard); window.removeEventListener("pageshow", restored); };
  }, []);

  useEffect(() => { if (showDetails) details.current?.focus(); }, [showDetails]);

  function clear() {
    request.current?.abort();
    setUpload(null); setProcessing(false); setShowDetails(false); setError("");
    if (input.current) input.current.value = "";
  }

  async function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !limits) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setUpload(null); setShowDetails(false); setError(""); setProcessing(true);
    try {
      const assessment = await assessUpload(file, limits, job, controller.signal);
      if (!controller.signal.aborted) setUpload({ kind: "upload", name: "Uploaded candidate", score: assessment.scoring.score, filename: file.name, assessment });
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof ResumeError || failure instanceof AssessmentError ? failure.message : "Assessment could not be completed. Check the connection and try again.");
    } finally {
      if (!controller.signal.aborted) setProcessing(false);
      if (input.current) input.current.value = "";
    }
  }

  const rows: Row[] = sortByMatchScore<Row>([
    ...candidates.map((candidate): DemoRow => ({ kind: "demo", name: candidate.display_name, score: candidate.match_score, candidate })),
    ...(upload ? [upload] : []),
  ]);

  return <>
    <section className="mission-role-heading"><div><p className="mission-kicker">SYNTHETIC DEMO ROLE / {job.client}</p><h1>{job.title}<span>.</span></h1><p>{job.description}</p></div><div className="mission-role-stamp"><small>ROLE FILE</small><strong>{job.id.replace("demo_", "").toUpperCase()}</strong><small>{candidates.length} DEMO PROFILES</small></div></section>
    <JobTabs jobId={job.id} active="candidates" count={rows.length} />
    <section className="mission-pool-heading"><div><p className="mission-kicker">CANDIDATE POOL / {candidates.length} SYNTHETIC PROFILES</p><h2>People for this role<span>.</span></h2><p>Available point scores sort highest first. Candidates without a point score follow alphabetically. A range is unresolved, not a zero.</p></div><button type="button" className="mission-button mission-upload" disabled={!limits || processing} onClick={() => input.current?.click()}>＋ Add resume PDF</button><input ref={input} id="candidate-resume" className="sr-only" tabIndex={-1} type="file" accept=".pdf,application/pdf" disabled={!limits || processing} aria-describedby="candidate-upload-help" onChange={selectFile} /></section>
    <p id="candidate-upload-help" className="mission-help">Choose a text-based PDF you have permission to process. Selection immediately sends it to the backend’s configured AI provider when Bedrock mode is active. Results need human review and clear on refresh. Scanned and password-protected PDFs are unsupported.</p>
    <p className="mission-upload-state" role="status">{processing ? <>Assessing the selected PDF… <button type="button" onClick={clear}>Cancel</button></> : upload ? <>New candidate added for this session. <button type="button" onClick={clear}>Clear upload</button></> : limits ? `PDF limit: ${(limits.max_bytes / (1024 * 1024)).toFixed(1)} MiB · ${limits.max_pages} pages` : <>Loading PDF limits… <button type="button" onClick={() => { setError(""); setLimitsAttempt((value) => value + 1); }}>Retry</button></>}</p>
    {error && <p role="alert" className="mission-error">{error}</p>}
    <div className="mission-table-panel"><div className="mission-table-bar"><div><span>▦</span><strong>Candidate overview</strong><small>{rows.length}</small></div><small>JOB-SPECIFIC VIEW</small></div><div className="mission-table-scroll"><table className="mission-table"><thead><tr><th scope="col">Candidate name</th><th scope="col">Title</th><th scope="col">Experience years</th><th scope="col">Match score</th><th scope="col">Source</th><th scope="col">Action</th></tr></thead><tbody>
      {rows.map((row) => <tr key={row.kind === "demo" ? row.candidate.id : "uploaded"} className={row.kind === "upload" ? "mission-new-row" : ""}>
        <td><div className="mission-person"><span className="mission-avatar">{row.kind === "demo" ? row.name.split(" ").map((part) => part[0]).join("") : "↑"}</span><div>{row.kind === "demo" ? <Link href={`/jobs/${job.id}/candidates/${row.candidate.id}`}>{row.name}</Link> : <button type="button" onClick={() => setShowDetails(true)}>{row.name} <b>JUST ADDED</b></button>}<small>{row.kind === "demo" ? "Synthetic demo candidate" : row.filename}</small></div></div></td>
        <td>{row.kind === "demo" ? row.candidate.headline : "Not extracted"}</td>
        <td>{row.kind === "demo" && row.candidate.stated_experience ? <>{row.candidate.stated_experience}<small className="mission-stated">stated</small></> : <span className="mission-muted">Unknown</span>}</td>
        <td><Score score={row.score} lower={row.kind === "upload" ? row.assessment.scoring.lower : row.candidate.score_lower} upper={row.kind === "upload" ? row.assessment.scoring.upper : row.candidate.score_upper} available={row.kind === "upload" || row.candidate.snapshot_available} /></td>
        <td><span className="mission-tag">{row.kind === "demo" ? "Demo" : "Temporary"}</span></td>
        <td>{row.kind === "demo" ? <Link className="mission-outline-button" href={`/jobs/${job.id}/candidates/${row.candidate.id}`}>View details ↗</Link> : <button type="button" className="mission-outline-button" onClick={() => setShowDetails(true)}>View details ↗</button>}</td>
      </tr>)}
    </tbody></table></div><div className="mission-table-foot"><span>Demo scores come from the last validated snapshot.</span><span>Uploaded results clear on refresh or navigation.</span></div></div>
    {upload && showDetails && <section ref={details} tabIndex={-1} aria-labelledby="uploaded-candidate-heading" className="mission-detail-panel"><div className="mission-detail-top"><div><p className="mission-kicker">TEMPORARY CANDIDATE / SOURCE REVIEW</p><h2 id="uploaded-candidate-heading">Uploaded candidate</h2><p>Identity and title are not in the current extraction contract. Review the source evidence before using this assessment.</p></div><button type="button" className="mission-outline-button" onClick={() => setShowDetails(false)}>Close details</button></div><AssessmentResult assessment={upload.assessment} job={job} /></section>}
    <p className="mission-review-note">Assessments support human review. Screening will be added after consent and text alternative workflows are ready.</p>
  </>;
}

export function CandidatePoolView({ jobId }: { jobId: string }) {
  const decode = useCallback((value: unknown) => decodeCandidatePool(value, jobId), [jobId]);
  const pool = useCatalog(`/jobs/${encodeURIComponent(jobId)}/candidates`, decode);
  const job = useCatalog(`/jobs/${encodeURIComponent(jobId)}`, decodeJob);
  if (pool.resource.status === "loading" || job.resource.status === "loading") return <CatalogLoading label="Loading the candidate pool…" />;
  if (pool.resource.status === "error") return pool.resource.notFound ? <CatalogNotFound /> : <CatalogUnavailable retry={pool.retry} subject="candidate pool" />;
  if (job.resource.status === "error") return job.resource.notFound ? <CatalogNotFound /> : <CatalogUnavailable retry={job.retry} subject="job details" />;
  return <CandidateWorkspace key={jobId} job={job.resource.data} candidates={pool.resource.data.candidates} />;
}
