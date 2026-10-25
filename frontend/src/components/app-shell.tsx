import Link from "next/link";
import { MissionTopbar } from "@/components/mission-topbar";
import { Navigation } from "@/components/navigation";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mission-app">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <aside className="mission-sidebar">
        <Link href="/" aria-label="Talent Insight home" className="mission-brand">
          <span aria-hidden="true" className="mission-brand-mark">✳</span>
          <span>talent insight<span className="mission-accent">.</span></span>
        </Link>
        <p className="mission-side-caption">WORKSPACE / 01</p>
        <Navigation />
        <div className="mission-side-footer">
          <p>Built around evidence.</p>
          <small>A little more clarity.<br />A more thoughtful conversation.</small>
        </div>
      </aside>
      <div className="mission-body">
        <MissionTopbar />
        <main id="main-content" tabIndex={-1} className="mission-main">
          {children}
        </main>
        <footer className="mission-footer">
          <p>Talent Insight · Mission workspace</p>
          <p>People make the final hiring decisions.</p>
        </footer>
      </div>
    </div>
  );
}
