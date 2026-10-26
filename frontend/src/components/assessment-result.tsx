"use client";

import { useState } from "react";
import { splitResume } from "@/lib/candidates";
import type { JobDetail } from "@/lib/catalog";
import type { Assessment, Citation, JudgmentStatus } from "@/lib/assessments";

const labels: Record<JudgmentStatus, string> = { met: "Supported", partial: "Partly supported", not_met: "Evidence does not meet this requirement", unknown: "Needs verification" };

export function AssessmentResult({ assessment, job }: { assessment: Assessment; job: JobDetail }) {
  const [selected, setSelected] = useState<Citation | null>(null);
  const { structured, judgments, scoring } = assessment;
  const questions = job.questions.filter((question) => question.requirement_ids.some((id) =>
    judgments.some((row) => row.requirement_id === id && row.status !== "met")));
  const strengths = judgments.filter((row) => row.status === "met" || row.status === "partial");
  const gaps = judgments.filter((row) => row.status === "unknown" || row.status === "not_met" || row.status === "partial");
  return (
    <article aria-labelledby="assessment-heading" className="mt-6 min-w-0 border-t border-[#e5e8df] pt-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="assessment-heading" className="text-lg font-semibold">Assessment · {structured.source.kind === "synthetic_demo" ? "precomputed demo" : "temporary upload"}</h3>
          <p className="mt-2 text-xs leading-6 text-[#59665d]">{structured.mode === "mock" ? "Mock mode · no interpreted match" : "AI interpretation · check each judgment against the source"}</p>
        </div>
        <span className="rounded-full bg-[#edf1e5] px-3 py-1 text-xs font-medium text-[#315943]">Human review required</span>
      </div>
      <p className="mt-4 text-sm leading-7 text-[#475a49]">{assessment.notice}</p>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg bg-[#f6f7f2] p-4"><p className="text-xs font-semibold text-[#59665d]">Assessment score</p><p className="mt-2 text-xl font-semibold">{scoring.score === null ? "Unavailable" : `${scoring.score.toFixed(1)} / 100`}</p></div>
        <div className="rounded-lg bg-[#f6f7f2] p-4"><p className="text-xs font-semibold text-[#59665d]">Possible range</p><p className="mt-2 text-xl font-semibold">{scoring.lower === null ? "Unavailable" : `${scoring.lower.toFixed(1)}–${scoring.upper?.toFixed(1)} / 100`}</p></div>
        <div className="rounded-lg bg-[#f6f7f2] p-4"><p className="text-xs font-semibold text-[#59665d]">Mandatory coverage</p><p className="mt-2 text-xl font-semibold">{scoring.mandatory_met} / {scoring.mandatory_total}</p></div>
      </div>
      <p className="mt-3 text-xs leading-6 text-[#59665d]">{scoring.resolved_count} of {judgments.length} requirements interpreted; {scoring.unknown_count} unknown. The range treats unknowns as unresolved, not as missing skills. The rubric is unvalidated and is not a hiring decision or performance probability.</p>

      <div className="mt-7 grid gap-5 lg:grid-cols-2">
        <section aria-labelledby="strengths-heading" className="min-w-0 rounded-lg border border-[#dce1d7] p-5">
          <h4 id="strengths-heading" className="font-semibold">Supported and partial evidence</h4>
          {strengths.length ? <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-[#475a49]">{strengths.map((row) => <li key={row.requirement_id}>{job.requirements.find((req) => req.id === row.requirement_id)?.description} · {labels[row.status]}</li>)}</ul> : <p className="mt-3 text-sm leading-6 text-[#59665d]">No supported requirements established by this assessment.</p>}
        </section>
        <section aria-labelledby="gaps-heading" className="min-w-0 rounded-lg border border-[#dce1d7] p-5">
          <h4 id="gaps-heading" className="font-semibold">Verification gaps</h4>
          {gaps.length ? <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-[#475a49]">{gaps.map((row) => <li key={row.requirement_id}>{job.requirements.find((req) => req.id === row.requirement_id)?.description} · {labels[row.status]}</li>)}</ul> : <p className="mt-3 text-sm leading-6 text-[#59665d]">No unresolved requirement in this assessment; still review the source and interpretation.</p>}
        </section>
      </div>

      <section aria-labelledby="judgments-heading" className="mt-7">
        <h4 id="judgments-heading" className="font-semibold">Requirement by requirement</h4>
        <p className="mt-2 text-xs leading-6 text-[#59665d]">Reasons are model interpretation in AI mode. Quotes are literal source text; a citation shows location, not competence.</p>
        <ol className="mt-4 space-y-4">
          {job.requirements.map((req) => {
            const row = judgments.find((item) => item.requirement_id === req.id)!;
            return <li key={req.id} className="min-w-0 rounded-lg border border-[#dce1d7] p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-2"><h5 className="max-w-2xl text-sm font-semibold leading-6">{req.description}</h5><span className="rounded-full bg-[#edf1e5] px-3 py-1 text-xs font-medium text-[#315943]">{labels[row.status]}</span></div>
              <p className="mt-2 text-xs capitalize text-[#59665d]">{req.category}</p>
              <p className="mt-3 text-sm leading-7 text-[#475a49]">{row.reason}</p>
              {row.fact_indices.length > 0 && <ul className="mt-4 space-y-4">{row.fact_indices.flatMap((index) => structured.facts[index].evidence.map((citation, evidenceIndex) =>
                <li key={`${index}-${evidenceIndex}`} className="min-w-0 border-l-2 border-[#b7c9a2] pl-4">
                  <p className="text-xs font-semibold text-[#466344]">{structured.facts[index].kind} · page {citation.page_number}</p>
                  <blockquote className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#475a49] [overflow-wrap:anywhere]">{citation.quote}</blockquote>
                  <a href="#assessment-source" onClick={() => setSelected(citation)} className="mt-2 inline-flex min-h-12 items-center rounded-sm text-xs font-semibold text-[#315943] underline underline-offset-4">View excerpt in source</a>
                </li>))}</ul>}
            </li>;
          })}
        </ol>
      </section>

      <section aria-labelledby="followups-heading" className="mt-7 rounded-lg border border-[#dce1d7] p-5">
        <h4 id="followups-heading" className="font-semibold">Job questions for follow-up</h4>
        <p className="mt-2 text-xs leading-6 text-[#59665d]">Existing questions linked to requirements needing more review; ask the candidate and verify answers independently.</p>
        {questions.length ? <ol className="mt-3 list-decimal space-y-3 pl-5 text-sm leading-7 text-[#475a49]">{questions.map((question) => <li key={question.id}>{question.text}</li>)}</ol> : <p className="mt-3 text-sm text-[#59665d]">No linked job questions for unresolved requirements.</p>}
      </section>

      <section id="assessment-source" tabIndex={-1} aria-labelledby="assessment-source-heading" className="mt-7 min-w-0 rounded-lg border border-[#dce1d7] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3"><h4 id="assessment-source-heading" className="font-semibold">Source text · {structured.source.kind === "synthetic_demo" ? "synthetic demo" : "uploaded PDF"}</h4>{selected && <button type="button" onClick={() => setSelected(null)} className="min-h-12 rounded-lg border border-[#9aac8b] px-4 text-sm font-medium">Clear highlight</button>}</div>
        <p className="mt-2 text-xs leading-6 text-[#59665d]">Compare with the original document. PDF reading order and scanned pages may be incomplete. Highlight offsets count Unicode characters.</p>
        {selected && <p role="status" className="mt-3 text-sm font-medium text-[#466344]">Highlighted excerpt on page {selected.page_number}</p>}
        <div className="mt-4 max-h-[36rem] overflow-y-auto rounded-lg bg-[#f6f7f2] p-4 sm:p-5">
          {structured.source.pages.map((page) => {
            const parts = selected?.page_number === page.page_number ? splitResume(page.text, selected.start, selected.end) : null;
            return <section key={page.page_number} className="mb-6 last:mb-0" aria-label={`Page ${page.page_number}`}><h5 className="text-xs font-semibold text-[#466344]">Page {page.page_number}</h5><pre className="mt-2 whitespace-pre-wrap font-sans text-sm leading-7 text-[#475a49] [overflow-wrap:anywhere]">{parts ? <>{parts.before}<mark className="rounded-sm bg-[#f2e8b2] text-[#243c2e]">{parts.excerpt}</mark>{parts.after}</> : page.text || "No extractable text on this page."}</pre></section>;
          })}
        </div>
      </section>
    </article>
  );
}
