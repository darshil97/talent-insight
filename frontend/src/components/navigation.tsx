"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/icon";

const links = [
  { href: "/", label: "Overview", icon: "overview" },
  { href: "/jobs", label: "Jobs", icon: "briefcase" },
  { href: "/guide", label: "How it works", icon: "book" },
] as const;

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav aria-label="Main navigation">
      <ul className="flex flex-wrap gap-2 lg:flex-col">
        {links.map(({ href, label, icon }) => (
          <li key={href} className="min-w-0 grow lg:grow-0">
            <Link
              href={href}
              aria-current={pathname === href || (href === "/jobs" && pathname.startsWith("/jobs/")) ? "page" : undefined}
              className={`flex min-h-12 items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition-colors ${
                pathname === href || (href === "/jobs" && pathname.startsWith("/jobs/"))
                  ? "bg-[#dce8cb] text-[#203e31]"
                  : "text-[#dae5de] hover:bg-white/10 hover:text-white"
              }`}
            >
              <Icon name={icon} />
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
