"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
const links = [
  { href: "/", label: "Overview", icon: "◫" },
  { href: "/jobs", label: "Jobs", icon: "▤" },
  { href: "/guide", label: "How it works", icon: "◇" },
] as const;

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav aria-label="Main navigation">
      <ul className="mission-nav-list">
        {links.map(({ href, label, icon }) => (
          <li key={href}>
            <Link
              href={href}
              aria-current={pathname === href || (href === "/jobs" && pathname.startsWith("/jobs/")) ? "page" : undefined}
              className={`mission-nav-link ${
                pathname === href || (href === "/jobs" && pathname.startsWith("/jobs/"))
                  ? "mission-nav-active"
                  : ""
              }`}
            >
              <span aria-hidden="true">{icon}</span>
              {label}
              {href === "/jobs" && <em>04</em>}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
