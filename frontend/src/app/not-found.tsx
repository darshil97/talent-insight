import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Page not found",
  description: "Return to the Talent Insight overview or workflow guide.",
};

export default function NotFound() {
  return (
    <div className="py-12">
      <p className="eyebrow">PAGE NOT FOUND</p>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">Let’s get you back on track.</h1>
      <p className="mt-4 max-w-lg text-base leading-7 text-[#59665d]">This page isn’t available. Visit the overview or workflow guide to explore Talent Insight.</p>
      <Link href="/" className="mt-7 inline-flex min-h-12 items-center rounded-lg bg-[#203e31] px-5 py-3 text-sm font-medium text-white hover:bg-[#315943]">Back to overview</Link>
    </div>
  );
}
