import type { Metadata } from "next";
import { JobsList } from "@/components/jobs-list";

export const metadata: Metadata = { title: "Jobs", description: "Explore curated synthetic technical roles and their requirements." };

export default function Jobs() {
  return <JobsList />;
}
