"use client";

import Link from "next/link";
import { CatalogLoading, CatalogNotFound, CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { decodeJob, type RequirementCategory } from "@/lib/catalog";
import { ResumeUpload } from "@/components/resume-upload";

const categories: { key: RequirementCategory; label: string }[] = [
  { key: "mandatory", label: "Mandatory requirements" },
  { key: "experience", label: "Experience" },
  { key: "preferred", label: "Preferred skills" },
  { key: "qualification", label: "Qualifications" },
];

export function JobDetailView({ jobId }: { jobId: string }) {
  const { resource, retry } = useCatalog(`/jobs/${encodeURIComponent(jobId)}`, decodeJob);
  if (resource.status === "loading") return <CatalogLoading />;
  if (resource.status === "error") return resource.notFound ? <CatalogNotFound /> : <CatalogUnavailable retry={retry} />;
  const job = resource.data;
  return (
    <>
      <p role="status" className="sr-only">{job.title} loaded.</p>
      <section aria-labelledby="role-heading" className="rounded-2xl border border-[#d7dfcb] bg-[#e9eedf] p-6 sm:p-8">
        <span className="inline-block rounded-full border border-[#becbad] px-3 py-1 text-xs font-medium text-[#466344]">Synthetic demo job</span>
        <h2 id="role-heading" className="mt-5 text-2xl font-semibold tracking-tight sm:text-3xl">{job.title}</h2>
        <p className="mt-2 text-sm font-medium text-[#475a49]">{job.client}</p>
        <p className="mt-5 max-w-3xl whitespace-pre-line text-sm leading-7 text-[#475a49]">{job.description}</p>
        <ul aria-label="Skills" className="mt-5 flex flex-wrap gap-2">
          {job.skills.map((skill, index) => <li key={`${skill}-${index}`} className="rounded-md bg-white/70 px-3 py-1 text-xs leading-5 text-[#475a49]">{skill}</li>)}
        </ul>
        <Link href={`/jobs/${job.id}/candidates`} className="mt-6 inline-flex min-h-12 items-center rounded-lg bg-[#203e31] px-5 py-3 text-sm font-medium text-white hover:bg-[#315943]">Review demo candidates</Link>
      </section>
      <div className="mt-7 grid gap-7 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section aria-labelledby="requirements-heading" className="rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
          <h2 id="requirements-heading" className="text-xl font-semibold">What the role calls for</h2>
          <p className="mt-3 text-sm leading-6 text-[#59665d]">Job requirements for human review. No candidate has been assessed.</p>
          {categories.map(({ key, label }) => {
            const requirements = job.requirements.filter((row) => row.category === key);
            return (
              <div key={key} className="mt-6 border-t border-[#e5e8df] pt-5">
                <h3 className="text-sm font-semibold">{label}</h3>
                {requirements.length ? <ul className="mt-3 list-disc space-y-3 pl-5 text-sm leading-7 text-[#59665d]">
                  {requirements.map((row) => <li key={row.id}>{row.description}{row.minimum_years !== null && <span className="mt-1 block text-xs font-medium text-[#466344]">Minimum relevant experience: {row.minimum_years} {row.minimum_years === 1 ? "year" : "years"}</span>}</li>)}
                </ul> : <p className="mt-3 text-sm text-[#59665d]">No requirements specified in this category.</p>}
              </div>
            );
          })}
        </section>
        <div className="space-y-7">
          <section aria-labelledby="criteria-heading" className="rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
            <h2 id="criteria-heading" className="text-lg font-semibold">Screening focus</h2>
            {job.screening_criteria.length ? <ul className="mt-4 list-disc space-y-3 pl-5 text-sm leading-7 text-[#59665d]">{job.screening_criteria.map((criterion, index) => <li key={index}>{criterion}</li>)}</ul> : <p className="mt-4 text-sm text-[#59665d]">No screening criteria specified.</p>}
          </section>
          <section aria-labelledby="questions-heading" className="rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
            <h2 id="questions-heading" className="text-lg font-semibold">Questions to explore</h2>
            <p className="mt-2 text-xs leading-6 text-[#59665d]">Prepared questions for recruiter review. AI screening is not available yet.</p>
            {job.questions.length ? <ol className="mt-4 list-decimal space-y-4 pl-5 text-sm leading-7 text-[#59665d]">{job.questions.map((question) => <li key={question.id}>{question.text}</li>)}</ol> : <p className="mt-4 text-sm text-[#59665d]">No questions specified.</p>}
          </section>
        </div>
      </div>
      <ResumeUpload key={job.id} />
      <p className="mt-7 rounded-xl border border-dashed border-[#cbd3c3] p-5 text-sm leading-7 text-[#59665d]">You can review this job’s synthetic candidate pool or inspect text from a temporary resume upload. Assessments remain in development. People make the final hiring decisions.</p>
    </>
  );
}
