"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCatalog } from "@/components/catalog-resource";
import { decodeJobs } from "@/lib/catalog";
const links = [
  { href: "/", label: "Overview", icon: "◫" },
  { href: "/jobs", label: "Jobs", icon: "▤" },
  { href: "/guide", label: "How it works", icon: "◇" },
] as const;

function JobsCount() {
  const { resource } = useCatalog("/jobs", decodeJobs);
  return resource.status === "ready" ? <em>{String(resource.data.length).padStart(2, "0")}</em> : null;
}

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
              {href === "/jobs" && pathname.startsWith("/jobs") && <JobsCount />}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
