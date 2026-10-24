import type { Metadata } from "next";
import { JobsList } from "@/components/jobs-list";

export const metadata: Metadata = { title: "Jobs", description: "Explore curated synthetic technical roles and their requirements." };

export default function Jobs() {
  return (
    <>
      <p className="eyebrow">JOB CATALOG</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Start with the role.</h1>
      <p className="mt-4 mb-8 max-w-2xl text-base leading-7 text-[#59665d]">Explore job requirements before reviewing candidate evidence. All roles and clients in this catalog are synthetic demo data, not active vacancies.</p>
      <JobsList />
    </>
  );
}
