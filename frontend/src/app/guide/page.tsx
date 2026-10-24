import type { Metadata } from "next";
import Link from "next/link";
import { Icon } from "@/components/icon";

export const metadata: Metadata = {
  title: "How it works",
  description: "The planned Talent Insight workflow and principles for reviewing job-related evidence.",
};

const stages = [
  {
    title: "Choose a job",
    description: "Begin with a curated technical role and its requirements. Job browsing is available now; all roles and clients are clearly identified as synthetic demo data.",
  },
  {
    title: "Review candidate evidence",
    description: "Open a job’s synthetic candidate pool, then inspect a profile and its source resume excerpts. Candidate review is available now. Temporary resume uploads will come later.",
  },
  {
    title: "Explore the match",
    description: "Inspect supporting excerpts and verification gaps alongside a transparent, deterministic assessment. Missing resume evidence means unknown; it does not prove a skill is absent.",
  },
  {
    title: "Have a focused conversation",
    description: "Optional AI screening will require consent and offer a text alternative. A report will distinguish resume evidence from candidate statements for human review.",
  },
];

export default function Guide() {
  return (
    <>
      <p className="eyebrow">HOW IT WORKS</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">From requirements to better questions.</h1>
      <p className="mt-4 max-w-2xl text-base leading-7 text-[#59665d]">Browse demo jobs and candidate evidence today, then explore the planned assessment workflow below. Resume uploads, matching and screening are still in development.</p>

      <section aria-labelledby="journey-heading" className="mt-9 rounded-2xl border border-[#dce1d7] bg-white p-6 sm:p-8">
        <h2 id="journey-heading" className="text-lg font-semibold">The planned recruiting journey</h2>
        <ol className="mt-6 divide-y divide-[#e5e8df]">
          {stages.map(({ title, description }, index) => (
            <li key={title} className="flex gap-4 py-6 first:pt-0 last:pb-0 sm:gap-6">
              <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-[#edf1e5] font-mono text-xs text-[#466344]">0{index + 1}</span>
              <div>
                <h3 className="text-base font-semibold">{title}</h3>
                <p className="mt-2 max-w-2xl text-sm leading-7 text-[#59665d]">{description}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="principles-heading" className="mt-7 rounded-2xl border border-[#d7dfcb] bg-[#e9eedf] p-6 sm:p-8">
        <p className="eyebrow">THE PRINCIPLES BEHIND THE WORK</p>
        <h2 id="principles-heading" className="mt-3 text-xl font-semibold">Evidence informs. People decide.</h2>
        <ul className="mt-5 grid list-disc gap-3 pl-5 text-sm leading-7 text-[#475a49]">
          <li>Assess job-related evidence. Do not infer protected traits, personality or performance from names, photos or voice.</li>
          <li>Keep evidence, interpretation and score calculation distinct. A match score will support review, not make a hiring decision.</li>
          <li>Uploaded resumes and results are planned to be temporary, with frontend results cleared on refresh. Uploads are not available yet; this site currently accepts no candidate data.</li>
        </ul>
      </section>
      <Link href="/" className="mt-7 inline-flex min-h-12 items-center gap-3 rounded-lg px-1 text-sm font-semibold text-[#315943] underline decoration-[#9aac8b] underline-offset-4 hover:text-[#203e31]">Back to overview <Icon name="arrow" /></Link>
    </>
  );
}
