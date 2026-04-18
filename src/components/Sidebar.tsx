"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: "🏠" },
  { href: "/wiki", label: "All Pages", icon: "📖" },
  { href: "/ask", label: "Ask a Question", icon: "💬" },
  { href: "/conflicts", label: "Conflicts", icon: "⚠️" },
  { href: "/admin", label: "Admin", icon: "⚙️" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 bg-[var(--color-wiki-sidebar)] border-r border-[var(--color-wiki-border)] min-h-screen flex flex-col">
      <div className="p-4 border-b border-[var(--color-wiki-border)]">
        <Link href="/" className="text-lg font-bold text-[var(--color-wiki-infobox-header)] no-underline">
          Spirits Wiki
        </Link>
      </div>
      <nav className="flex-1 p-2">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2 px-3 py-2 rounded text-sm no-underline mb-0.5 ${
                isActive
                  ? "bg-[var(--color-wiki-accent)] text-white"
                  : "text-gray-700 hover:bg-gray-200"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-[var(--color-wiki-border)] text-xs text-gray-500">
        Private Lore Reference
      </div>
    </aside>
  );
}
