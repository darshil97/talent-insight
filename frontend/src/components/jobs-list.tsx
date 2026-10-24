"use client";

import Link from "next/link";
import { CatalogLoading, CatalogUnavailable, useCatalog } from "@/components/catalog-resource";
import { Icon } from "@/components/icon";
import { decodeJobs } from "@/lib/catalog";

export function JobsList() {
  const { resource, retry } = useCatalog("/jobs", decodeJobs);
  if (resource.status === "loading") return <CatalogLoading />;
  if (resource.status === "error") return <CatalogUnavailable retry={retry} />;
  if (resource.data.length === 0) {
    return (
      <section className="rounded-xl border border-[#dce1d7] bg-white p-8">
        <h2 className="text-xl font-semibold">No jobs in the catalog yet.</h2>
        <p className="mt-3 text-sm leading-7 text-[#59665d]">There are no roles to review right now. Check again later.</p>
        <button type="button" onClick={retry} className="mt-5 min-h-12 rounded-lg border border-[#9aac8b] px-5 text-sm font-medium">Refresh jobs</button>
      </section>
    );
  }
  return (
    <>
      <p role="status" className="mb-5 text-sm text-[#59665d]">{resource.data.length} {resource.data.length === 1 ? "role" : "roles"} to explore</p>
      <ul className="grid gap-5 xl:grid-cols-2">
        {resource.data.map((job) => (
          <li key={job.id} className="flex flex-col rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
            <div className="mb-5 flex items-center justify-between gap-3">
              <span className="grid size-10 place-items-center rounded-lg bg-[#edf1e5] text-[#466344]"><Icon name="briefcase" /></span>
              <span className="rounded-full bg-[#edf1e5] px-3 py-1 text-xs font-medium text-[#466344]">Synthetic demo job</span>
            </div>
            <h2 className="text-xl font-semibold tracking-tight"><Link href={`/jobs/${job.id}`} className="rounded-sm hover:underline underline-offset-4">{job.title}</Link></h2>
            <p className="mt-2 text-sm text-[#59665d]">{job.client}</p>
            <p className="mt-4 text-sm leading-7 text-[#59665d]">{job.description}</p>
            <ul aria-label={`${job.title} skills`} className="mt-5 flex flex-wrap gap-2">
              {job.skills.map((skill, index) => <li key={`${skill}-${index}`} className="rounded-md border border-[#e0e5d9] bg-[#f7f8f2] px-2.5 py-1 text-xs leading-5 text-[#475a49]">{skill}</li>)}
            </ul>
            <p className="mt-auto flex items-center gap-2 pt-6 text-xs text-[#59665d]"><Icon name="evidence" />Open the role title to review requirements</p>
          </li>
        ))}
      </ul>
    </>
  );
}
