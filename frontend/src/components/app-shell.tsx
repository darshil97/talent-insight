import Link from "next/link";
import { Navigation } from "@/components/navigation";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <aside className="flex flex-col bg-[#203e31] px-5 py-5 text-white lg:sticky lg:top-0 lg:h-dvh lg:overflow-y-auto lg:px-6 lg:py-9">
        <Link href="/" aria-label="Talent Insight home" className="mb-6 flex min-h-11 w-fit items-center gap-3 rounded-sm lg:mb-12">
          <span aria-hidden="true" className="grid size-10 place-items-center rounded-xl border border-[#9fba9c] text-[#dce8cb]">
            <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M5 6h14M12 6v13M6 12h3m6 0h3" /><circle cx="12" cy="3" r="1" fill="currentColor" stroke="none" /></svg>
          </span>
          <span className="text-lg font-semibold tracking-tight">talent insight<span className="text-[#c7d9ad]">.</span></span>
        </Link>
        <p className="mb-3 hidden text-[11px] font-semibold tracking-[0.18em] text-[#b6c8bb] lg:block">WORKSPACE</p>
        <Navigation />
        <div className="mt-auto hidden pt-16 lg:block">
          <div className="border-t border-white/20 pt-6">
            <p className="text-sm font-medium text-[#dce8cb]">Built around evidence.</p>
            <p className="mt-2 text-xs leading-6 text-[#bfcec4]">A little more clarity.<br />A more thoughtful conversation.</p>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e0e4dc] bg-[#fafbf7] px-6 py-5 sm:px-10 lg:px-12">
          <p className="text-sm text-[#566458]">Your recruiting workspace</p>
          <span className="inline-flex items-center gap-2 rounded-full border border-[#dfdfc7] bg-[#f1f0df] px-3 py-1.5 text-xs font-medium text-[#656038]">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-[#827940]" />In development
          </span>
        </header>
        <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-7xl flex-1 px-6 py-9 sm:px-10 sm:py-12 lg:px-12">
          {children}
        </main>
        <footer className="mx-6 flex flex-wrap items-center justify-between gap-2 border-t border-[#dce1d7] py-5 text-xs leading-5 text-[#59665d] sm:mx-10 lg:mx-12">
          <p>Talent Insight · A considered approach to recruiting</p>
          <p>People make the final hiring decisions.</p>
        </footer>
      </div>
    </div>
  );
}
