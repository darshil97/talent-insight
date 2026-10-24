import Link from "next/link";
import { Icon } from "@/components/icon";

const steps = [
  {
    number: "01",
    icon: "briefcase",
    title: "Start with the role",
    description: "Understand the job requirements before reviewing a candidate.",
  },
  {
    number: "02",
    icon: "evidence",
    title: "Look at the evidence",
    description: "Explore relevant experience, supporting excerpts and open questions.",
  },
  {
    number: "03",
    icon: "conversation",
    title: "Make room for context",
    description: "Use focused follow-ups to help a person fill in the gaps.",
  },
] as const;

export default function Home() {
  return (
    <>
      <div className="mb-9">
        <p className="eyebrow">OVERVIEW</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">A clearer view of every candidate.</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-[#59665d]">Bring job requirements, candidate evidence and thoughtful questions into one place.</p>
      </div>

      <section aria-labelledby="welcome-heading" className="relative overflow-hidden rounded-2xl border border-[#d7dfcb] bg-[#e9eedf] p-7 sm:p-9">
        <div aria-hidden="true" className="pointer-events-none absolute -right-24 -top-24 size-80 rounded-full border border-[#cdd8be]" />
        <div aria-hidden="true" className="pointer-events-none absolute -right-12 -top-12 size-56 rounded-full border border-[#cdd8be]" />
        <div className="relative max-w-xl">
          <p className="eyebrow">EVIDENCE FIRST. PEOPLE ALWAYS.</p>
          <h2 id="welcome-heading" className="mt-5 max-w-md text-3xl leading-tight font-medium tracking-tight sm:text-4xl">Good recruiting starts<br className="hidden sm:block" /> with better understanding.</h2>
          <p className="mt-5 max-w-lg text-sm leading-7 text-[#475a49]">Talent Insight is being built to support technical recruiting with transparent, job-related evidence and space for human judgment.</p>
          <Link href="/jobs" className="mt-7 inline-flex min-h-12 items-center gap-4 rounded-lg bg-[#203e31] px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-[#315943]">Explore the job catalog <Icon name="arrow" /></Link>
        </div>
      </section>

      <section aria-labelledby="workflow-heading" className="mt-10">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
          <h2 id="workflow-heading" className="text-lg font-semibold tracking-tight">A more thoughtful workflow</h2>
          <span className="text-xs text-[#68715d]">Job browsing is available</span>
        </div>
        <ol className="grid gap-4 xl:grid-cols-3">
          {steps.map(({ number, icon, title, description }) => (
            <li key={number} className="rounded-xl border border-[#dce1d7] bg-white p-6">
              <div className="mb-6 flex items-center justify-between">
                <span className="grid size-10 place-items-center rounded-lg bg-[#f1f4ec] text-[#466344]"><Icon name={icon} /></span>
                <span className="font-mono text-xs text-[#6b776b]">{number}</span>
              </div>
              <h3 className="text-base font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-[#59665d]">{description}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="availability-heading" className="mt-7 flex flex-col gap-4 rounded-xl border border-dashed border-[#cbd3c3] p-6 sm:flex-row sm:items-start sm:gap-5">
        <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-[#e8ecdf] text-sm font-semibold text-[#526548]">i</span>
        <div>
          <h2 id="availability-heading" className="text-sm font-semibold">A workspace taking shape</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#59665d]">You can browse synthetic demo jobs, review their candidate pools and inspect source resume evidence. Resume upload, matching and screening are still in development and unavailable here.</p>
        </div>
      </section>
    </>
  );
}
