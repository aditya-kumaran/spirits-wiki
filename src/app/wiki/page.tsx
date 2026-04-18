"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import { ENTITY_TYPES } from "@/types";

interface PageSummary {
  slug: string;
  entityName: string;
  entityType: string;
  lastModified: string;
  versionNumber: number;
  origin: string;
  conflictStatus: string | null;
}

function WikiIndexContent() {
  const searchParams = useSearchParams();
  const typeFilter = searchParams.get("type");
  const searchQuery = searchParams.get("q") || "";

  const [pages, setPages] = useState<PageSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(searchQuery);

  useEffect(() => {
    const params = new URLSearchParams();
    if (typeFilter) params.set("type", typeFilter);
    if (searchQuery) params.set("q", searchQuery);

    fetch(`/api/pages?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => {
        setPages(data.pages || []);
        setTotal(data.total || 0);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [typeFilter, searchQuery]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const params = new URLSearchParams(window.location.search);
    if (search) params.set("q", search);
    else params.delete("q");
    window.history.pushState({}, "", `/wiki?${params.toString()}`);
    window.location.reload();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Wiki Pages</h1>
        <span className="text-sm text-gray-500">{total} pages</span>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search pages..."
          className="w-full px-3 py-2 border border-[var(--color-wiki-border)] rounded text-sm"
        />
      </form>

      {/* Type filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <Link
          href="/wiki"
          className={`px-3 py-1 rounded text-sm no-underline ${
            !typeFilter
              ? "bg-[var(--color-wiki-accent)] text-white"
              : "bg-gray-200 text-gray-700 hover:bg-gray-300"
          }`}
        >
          All
        </Link>
        {ENTITY_TYPES.map((t) => (
          <Link
            key={t}
            href={`/wiki?type=${t}`}
            className={`px-3 py-1 rounded text-sm no-underline capitalize ${
              typeFilter === t
                ? "bg-[var(--color-wiki-accent)] text-white"
                : "bg-gray-200 text-gray-700 hover:bg-gray-300"
            }`}
          >
            {t}
          </Link>
        ))}
      </div>

      {/* Page list */}
      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : pages.length === 0 ? (
        <p className="text-gray-500">
          No pages found. Run the ingestion pipeline to generate wiki pages
          from your .docx files.
        </p>
      ) : (
        <div className="space-y-1">
          {pages.map((page) => (
            <Link
              key={page.slug}
              href={`/wiki/${page.slug}`}
              className="flex items-center justify-between p-3 bg-white rounded border border-[var(--color-wiki-border)] hover:border-[var(--color-wiki-accent)] no-underline group"
            >
              <div>
                <span className="font-medium text-[var(--color-wiki-link)] group-hover:underline">
                  {page.entityName}
                </span>
                <span className="ml-2 text-xs px-2 py-0.5 bg-gray-100 rounded capitalize text-gray-600">
                  {page.entityType}
                </span>
                {page.conflictStatus === "pending" && (
                  <span className="ml-2 text-xs px-2 py-0.5 bg-yellow-100 text-yellow-800 rounded">
                    Conflict
                  </span>
                )}
              </div>
              <div className="text-xs text-gray-400">
                v{page.versionNumber} &middot;{" "}
                {new Date(page.lastModified).toLocaleDateString()}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function WikiIndex() {
  return (
    <Suspense fallback={<p className="text-gray-500">Loading...</p>}>
      <WikiIndexContent />
    </Suspense>
  );
}
