import Link from "next/link";

export function CandidateNotFound({ jobId }: { jobId: string }) {
  return (
    <section className="rounded-xl border border-[#dce1d7] bg-white p-8">
      <h2 className="text-xl font-semibold">Candidate or job not found</h2>
      <p className="mt-3 text-sm leading-7 text-[#59665d]">This profile isn’t available for the selected job. Return to its candidate pool or choose another job.</p>
      <div className="mt-5 flex flex-wrap gap-x-6">
        <Link href={`/jobs/${jobId}/candidates`} className="inline-flex min-h-12 items-center rounded-sm text-sm font-semibold text-[#315943] underline underline-offset-4">Back to candidate pool</Link>
        <Link href="/jobs" className="inline-flex min-h-12 items-center rounded-sm text-sm font-semibold text-[#315943] underline underline-offset-4">Browse jobs</Link>
      </div>
    </section>
  );
}
