"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface ConflictPage {
  slug: string;
  entityName: string;
  entityType: string;
  conflictStatus: string;
}

export default function ConflictsPage() {
  const [pages, setPages] = useState<ConflictPage[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/pages?limit=200")
      .then((r) => r.json())
      .then((data) => {
        const conflicting = (data.pages || []).filter(
          (p: ConflictPage) => p.conflictStatus === "pending"
        );
        setPages(conflicting);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500">Loading...</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Ingestion Conflicts</h1>
      <p className="text-sm text-gray-500 mb-4">
        These pages have unresolved conflicts — new source material was found
        but the pages have manual edits that would be overwritten. Review and
        resolve each conflict.
      </p>

      {pages.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded p-4 text-sm text-green-700">
          No unresolved conflicts. All pages are up to date.
        </div>
      ) : (
        <div className="space-y-2">
          {pages.map((page) => (
            <div
              key={page.slug}
              className="flex items-center justify-between p-3 bg-yellow-50 rounded border border-yellow-200"
            >
              <div>
                <Link
                  href={`/wiki/${page.slug}`}
                  className="font-medium text-[var(--color-wiki-link)] hover:underline"
                >
                  {page.entityName}
                </Link>
                <span className="ml-2 text-xs capitalize text-gray-500">
                  {page.entityType}
                </span>
              </div>
              <span className="text-xs px-2 py-1 bg-yellow-200 text-yellow-800 rounded">
                Pending Resolution
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
