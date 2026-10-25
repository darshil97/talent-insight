import Link from "next/link";

export function JobTabs({ jobId, active, count }: { jobId: string; active: "details" | "candidates"; count?: number }) {
  return <nav className="mission-tabs" aria-label="Job sections">
    <Link href={`/jobs/${jobId}`} aria-current={active === "details" ? "page" : undefined}>Job details</Link>
    <Link href={`/jobs/${jobId}/candidates`} aria-current={active === "candidates" ? "page" : undefined}>Candidates{count !== undefined && <span>{count}</span>}</Link>
  </nav>;
}
