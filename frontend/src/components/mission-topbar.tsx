"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function MissionTopbar() {
  const pathname = usePathname();
  const section = pathname === "/" ? "OVERVIEW" : pathname === "/jobs" ? "JOBS" : pathname === "/guide" ? "HOW IT WORKS" : pathname.endsWith("/candidates") ? "CANDIDATES" : pathname.includes("/candidates/") ? "CANDIDATE PROFILE" : "JOB DETAILS";
  return <header className="mission-topbar">
    <p>TALENT INSIGHT <span>/</span> {section}</p>
    <Link href="/guide">How it works ↗</Link>
  </header>;
}
