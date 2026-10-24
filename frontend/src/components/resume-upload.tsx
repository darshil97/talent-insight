"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { fetchCatalog } from "@/lib/catalog";
import { decodeResumeLimits, ResumeError, uploadResume, type ExtractedResume, type ResumeLimits } from "@/lib/resumes";

export function ResumeUpload() {
  const [limits, setLimits] = useState<ResumeLimits | null>(null);
  const [limitsAttempt, setLimitsAttempt] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ExtractedResume | null>(null);
  const request = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchCatalog("/resumes/limits", decodeResumeLimits, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setLimits(data); })
      .catch(() => { if (!controller.signal.aborted) setError("Upload limits could not be loaded. Try again."); });
    return () => controller.abort();
  }, [limitsAttempt]);

  useEffect(() => {
    // Also discard data before a browser history snapshot can retain the page.
    function discard() {
      request.current?.abort();
      setFile(null); setResult(null); setBusy(false); setError("");
      if (input.current) input.current.value = "";
    }
    window.addEventListener("pagehide", discard);
    function restored(event: PageTransitionEvent) { if (event.persisted) discard(); }
    window.addEventListener("pageshow", restored);
    return () => {
      request.current?.abort();
      window.removeEventListener("pagehide", discard);
      window.removeEventListener("pageshow", restored);
    };
  }, []);

  function clear() {
    request.current?.abort();
    setFile(null); setResult(null); setError(""); setBusy(false);
    if (input.current) { input.current.value = ""; input.current.focus(); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !limits) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setResult(null); setError(""); setBusy(true);
    try {
      const data = await uploadResume(file, limits, controller.signal);
      if (!controller.signal.aborted) {
        setResult(data); setFile(null);
        if (input.current) input.current.value = "";
      }
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof ResumeError ? failure.message : "The PDF could not be processed. Check the connection and try again.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section aria-labelledby="upload-heading" className="mt-7 min-w-0 rounded-xl border border-[#dce1d7] bg-white p-6 sm:p-7">
      <h2 id="upload-heading" className="text-xl font-semibold">Review a resume PDF</h2>
      <p id="upload-help" className="mt-3 text-sm leading-7 text-[#59665d]">Upload a text-based resume to inspect its extracted text for this role. No assessment or score is generated. Use documents you have permission to process.</p>
      <p className="mt-2 text-sm leading-7 text-[#59665d]">The application does not save uploads or extracted text. Results clear on refresh, leaving this job, or Clear. Scanned and password-protected PDFs are not supported.</p>
      <p className="mt-3 text-xs leading-6 text-[#59665d]">{limits ? `Limits: ${(limits.max_bytes / (1024 * 1024)).toLocaleString(undefined, { maximumFractionDigits: 2 })} MiB, ${limits.max_pages} pages, ${limits.max_characters.toLocaleString()} extracted characters.` : "Loading upload limits…"}</p>
      <form onSubmit={submit} className="mt-5 space-y-4">
        <label htmlFor="resume-pdf" className="block text-sm font-semibold">Resume PDF</label>
        <input ref={input} id="resume-pdf" type="file" accept=".pdf,application/pdf" aria-describedby="upload-help" disabled={!limits || busy}
          className="block min-h-12 w-full min-w-0 rounded-lg border border-[#cbd3c3] p-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-[#edf1e5] file:px-3 file:py-2 file:text-[#203e31]"
          onChange={(event) => { request.current?.abort(); setFile(event.target.files?.[0] ?? null); setResult(null); setError(""); }} />
        <div className="flex flex-wrap gap-3">
          <button type="submit" disabled={!file || !limits || busy} className="min-h-12 rounded-lg bg-[#203e31] px-5 py-3 text-sm font-medium text-white enabled:hover:bg-[#315943] disabled:opacity-50">{busy ? "Extracting text…" : "Extract resume text"}</button>
          <button type="button" onClick={clear} className="min-h-12 rounded-lg border border-[#cbd3c3] px-5 py-3 text-sm font-medium hover:bg-[#f1f4ec]">{busy ? "Cancel and clear" : "Clear"}</button>
          {!limits && <button type="button" onClick={() => { setError(""); setLimitsAttempt((value) => value + 1); }} className="min-h-12 rounded-lg border border-[#cbd3c3] px-4 text-sm">Retry upload setup</button>}
        </div>
      </form>
      <p role="status" className="mt-3 text-sm leading-6 text-[#59665d]">{busy ? "Processing PDF. You can cancel and clear at any time." : result ? `Text extracted from ${result.page_count} ${result.page_count === 1 ? "page" : "pages"}.` : ""}</p>
      {error && <p role="alert" className="mt-3 rounded-lg border border-[#dfc7bc] bg-[#fff7f2] p-4 text-sm leading-6 text-[#793d29]">{error}</p>}
      {result && <div className="mt-5 min-w-0 border-t border-[#e5e8df] pt-5">
        <h3 className="font-semibold">Extracted resume text · temporary</h3>
        <p className="mt-2 text-xs leading-6 text-[#59665d]">Review extraction accuracy against the original PDF. Formatting and reading order may differ. Text on image-only pages may be missing.</p>
        <div className="mt-4 max-h-[36rem] overflow-y-auto rounded-lg bg-[#f6f7f2] p-4 sm:p-6">
          {result.pages.map((page) => <section key={page.page_number} aria-label={`Page ${page.page_number}`} className="mb-6 last:mb-0">
            <h4 className="text-xs font-semibold text-[#466344]">Page {page.page_number}</h4>
            <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7 text-[#475a49] [overflow-wrap:anywhere]">{page.text.trim() ? page.text : "No extractable text on this page. It may be blank or scanned."}</p>
          </section>)}
        </div>
      </div>}
    </section>
  );
}
