"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { CatalogLoading, CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { CandidateNotFound } from "@/components/candidate-not-found";
import { decodeCandidateProfile, splitResume, type EvidenceClaim } from "@/lib/candidates";

const kinds = [
  { key: "experience", label: "Experience excerpts" },
  { key: "skill", label: "Skill excerpts" },
  { key: "qualification", label: "Qualification excerpts" },
] as const;

function EvidenceGroup({ kind, label, claims, onSelect }: {
  kind: EvidenceClaim["kind"];
  label: string;
  claims: EvidenceClaim[];
  onSelect: (claim: EvidenceClaim) => void;
}) {
  const rows = claims.filter((claim) => claim.kind === kind);
  return (
    <section className="min-w-0 rounded-xl border border-[#dce1d7] bg-white p-6">
      <h3 className="text-base font-semibold">{label}</h3>
      {rows.length ? (
        <ul className="mt-5 space-y-6">
          {rows.map((claim, index) => (
            <li key={`${claim.start}-${claim.label}-${index}`} className="border-t border-[#e5e8df] pt-5 first:border-0 first:pt-0">
              <h4 className="text-sm font-semibold">{claim.label}</h4>
              <blockquote className="mt-3 border-l-2 border-[#b7c9a2] pl-4 text-sm leading-7 whitespace-pre-wrap text-[#59665d] [overflow-wrap:anywhere]">{claim.quote}</blockquote>
              <a href="#resume-source" onClick={() => onSelect(claim)} className="mt-3 inline-flex min-h-12 items-center rounded-sm text-xs font-semibold text-[#315943] underline underline-offset-4" aria-label={`View ${claim.label} excerpt in source resume`}>View in source resume · chars {claim.start}–{claim.end}</a>
            </li>
          ))}
        </ul>
      ) : <p className="mt-4 text-sm leading-7 text-[#59665d]">No curated excerpts in this category. Review the source resume; this is not a finding that a requirement is unmet.</p>}
    </section>
  );
}

export function CandidateProfileView({ jobId, candidateId }: { jobId: string; candidateId: string }) {
  const decode = useCallback((value: unknown) => decodeCandidateProfile(value, jobId, candidateId), [jobId, candidateId]);
  const { resource, retry } = useCatalog(`/jobs/${encodeURIComponent(jobId)}/candidates/${encodeURIComponent(candidateId)}`, decode);
  const [selected, setSelected] = useState<EvidenceClaim | null>(null);
  if (resource.status === "loading") return <CatalogLoading label="Loading the candidate profile…" />;
  if (resource.status === "error") return resource.notFound ? <CandidateNotFound jobId={jobId} /> : <CatalogUnavailable retry={retry} subject="candidate profile" />;
  const { job, candidate } = resource.data;
  const highlighted = selected ? splitResume(candidate.resume_text, selected.start, selected.end) : null;

  return (
    <>
      <p role="status" className="sr-only">{candidate.display_name} profile loaded for {job.title}.</p>
      <section aria-labelledby="candidate-heading" className="rounded-2xl border border-[#d7dfcb] bg-[#e9eedf] p-6 sm:p-8">
        <span className="inline-block rounded-full border border-[#becbad] px-3 py-1 text-xs font-medium text-[#466344]">Synthetic demo candidate</span>
        <h2 id="candidate-heading" className="mt-5 text-2xl font-semibold sm:text-3xl">{candidate.display_name}</h2>
        <p className="mt-2 text-base text-[#475a49]">{candidate.headline}</p>
        <p className="mt-5 text-xs font-semibold text-[#59665d]">Authored demo summary</p>
        <p className="mt-2 text-sm leading-7 text-[#475a49]">{candidate.summary}</p>
        <p className="mt-5 text-sm text-[#475a49]">Reviewing for <Link href={`/jobs/${jobId}`} className="rounded-sm font-semibold underline underline-offset-4">{job.title}</Link> · {job.client}</p>
      </section>

      <section aria-labelledby="evidence-heading" className="mt-8">
        <h2 id="evidence-heading" className="text-xl font-semibold">Resume evidence</h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-[#59665d]">These are curated excerpts from the synthetic source resume. Read the full wording, including any limits or uncertainty. Missing evidence is unknown and does not prove a skill is absent.</p>
        <div className="mt-6 grid items-start gap-5 xl:grid-cols-2">
          <div className="min-w-0 space-y-5">
            {kinds.filter(({ key }) => key !== "skill").map(({ key, label }) => (
              <EvidenceGroup key={key} kind={key} label={label} claims={candidate.claims} onSelect={setSelected} />
            ))}
          </div>
          <EvidenceGroup kind="skill" label="Skill excerpts" claims={candidate.claims} onSelect={setSelected} />
        </div>
      </section>

      <section id="resume-source" tabIndex={-1} aria-labelledby="source-heading" className="mt-8 rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="source-heading" className="text-xl font-semibold">Source resume · synthetic demo</h2>
          {selected && <button type="button" onClick={() => setSelected(null)} className="min-h-12 rounded-lg border border-[#9aac8b] px-4 text-sm font-medium">Clear highlight</button>}
        </div>
        <p className="mt-3 text-xs leading-6 text-[#59665d]">Excerpt offsets count Unicode characters from zero; the end position is excluded. This text is displayed as source data.</p>
        {selected && <p role="status" className="mt-4 text-sm font-medium text-[#466344]">Highlighted excerpt: {selected.label}</p>}
        <pre className="mt-5 rounded-lg bg-[#f7f8f2] p-5 font-sans text-sm leading-8 whitespace-pre-wrap text-[#475a49] [overflow-wrap:anywhere]">{highlighted ? <>{highlighted.before}<mark className="rounded-sm bg-[#f2e8b2] text-[#243c2e]">{highlighted.excerpt}</mark>{highlighted.after}</> : candidate.resume_text}</pre>
      </section>
      <p className="mt-7 rounded-xl border border-dashed border-[#cbd3c3] p-5 text-sm leading-7 text-[#59665d]">This profile has not been matched or scored against the job. Resume uploads and assessments are still in development. People make the final hiring decisions.</p>
    </>
  );
}
