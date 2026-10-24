"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CatalogError, fetchCatalog } from "@/lib/catalog";

type Resource<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; notFound: boolean };

export function useCatalog<T>(path: string, decode: (value: unknown) => T) {
  const [resource, setResource] = useState<Resource<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchCatalog(path, decode, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setResource({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setResource({ status: "error", notFound: error instanceof CatalogError && error.kind === "not_found" });
        }
      });
    return () => controller.abort();
  }, [path, decode, attempt]);

  return {
    resource,
    retry: () => {
      setResource({ status: "loading" });
      setAttempt((value) => value + 1);
    },
  };
}

export function CatalogLoading({ label = "Loading the job catalog…" }: { label?: string }) {
  return <p role="status" className="rounded-xl border border-[#dce1d7] bg-white p-8 text-sm text-[#59665d]">{label}</p>;
}

export function CatalogNotFound() {
  return (
    <section className="rounded-xl border border-[#dce1d7] bg-white p-8">
      <h2 className="text-xl font-semibold">Job not found</h2>
      <p className="mt-3 text-sm leading-7 text-[#59665d]">This job isn’t in the catalog. Return to the list to choose another role.</p>
      <Link href="/jobs" className="mt-5 inline-flex min-h-12 items-center text-sm font-semibold text-[#315943] underline underline-offset-4">Back to jobs</Link>
    </section>
  );
}

export function CatalogUnavailable({ retry, subject = "job catalog" }: { retry: () => void; subject?: string }) {
  return (
    <section role="alert" className="rounded-xl border border-[#dfdfc7] bg-[#f5f3e7] p-8">
      <h2 className="text-xl font-semibold">The {subject} couldn’t be loaded.</h2>
      <p className="mt-3 max-w-xl text-sm leading-7 text-[#59665d]">Your connection or the catalog service may be unavailable. Try again in a moment.</p>
      <button type="button" onClick={retry} className="mt-5 min-h-12 rounded-lg bg-[#203e31] px-5 py-3 text-sm font-medium text-white hover:bg-[#315943]">Try again</button>
    </section>
  );
}
