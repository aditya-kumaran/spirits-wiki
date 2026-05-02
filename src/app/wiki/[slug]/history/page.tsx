"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import type { WikiVersion } from "@/types";

export default function HistoryPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [versions, setVersions] = useState<WikiVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedA, setSelectedA] = useState<string | null>(null);
  const [selectedB, setSelectedB] = useState<string | null>(null);
  const [diffContent, setDiffContent] = useState<{ old: string; new: string } | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/pages/${slug}/versions`)
      .then((r) => r.json())
      .then((data) => {
        setVersions(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [slug]);

  const handleCompare = async () => {
    if (!selectedA || !selectedB) return;
    const [a, b] = await Promise.all([
      fetch(`/api/pages/${slug}/versions?id=${selectedA}`).then((r) => r.json()),
      fetch(`/api/pages/${slug}/versions?id=${selectedB}`).then((r) => r.json()),
    ]);
    setDiffContent({ old: a.contentMarkdown, new: b.contentMarkdown });
  };

  const handleRestore = async (versionId: string) => {
    if (!confirm("Restore this version? A new version will be created.")) return;
    setRestoring(versionId);
    try {
      const res = await fetch(`/api/pages/${slug}/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: versionId }),
      });
      if (res.ok) {
        window.location.href = `/wiki/${slug}`;
      }
    } finally {
      setRestoring(null);
    }
  };

  if (loading) return <p className="text-gray-500">Loading history...</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Version History</h1>
        <Link
          href={`/wiki/${slug}`}
          className="text-sm text-[var(--color-wiki-link)] no-underline hover:underline"
        >
          Back to page
        </Link>
      </div>

      {/* Compare controls */}
      {versions.length >= 2 && (
        <div className="mb-4 flex items-center gap-2">
          <select
            value={selectedA || ""}
            onChange={(e) => setSelectedA(e.target.value)}
            className="px-2 py-1 border border-gray-300 rounded text-sm"
          >
            <option value="">Select version A...</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                v{v.versionNumber} - {new Date(v.createdAt).toLocaleString()}
              </option>
            ))}
          </select>
          <span className="text-gray-400">vs</span>
          <select
            value={selectedB || ""}
            onChange={(e) => setSelectedB(e.target.value)}
            className="px-2 py-1 border border-gray-300 rounded text-sm"
          >
            <option value="">Select version B...</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                v{v.versionNumber} - {new Date(v.createdAt).toLocaleString()}
              </option>
            ))}
          </select>
          <button
            onClick={handleCompare}
            disabled={!selectedA || !selectedB}
            className="px-3 py-1 bg-[var(--color-wiki-accent)] text-white rounded text-sm disabled:opacity-50"
          >
            Compare
          </button>
        </div>
      )}

      {/* Diff view */}
      {diffContent && (
        <div className="mb-6 border border-[var(--color-wiki-border)] rounded overflow-hidden">
          <div className="bg-gray-100 px-3 py-2 text-sm font-semibold border-b">
            Diff View
          </div>
          <div className="grid grid-cols-2 gap-0 text-xs font-mono">
            <div className="p-3 border-r border-gray-200 bg-red-50 whitespace-pre-wrap overflow-auto max-h-96">
              {diffContent.old}
            </div>
            <div className="p-3 bg-green-50 whitespace-pre-wrap overflow-auto max-h-96">
              {diffContent.new}
            </div>
          </div>
        </div>
      )}

      {/* Version list */}
      <div className="space-y-2">
        {versions.map((v) => (
          <div
            key={v.id}
            className="flex items-center justify-between p-3 bg-white rounded border border-[var(--color-wiki-border)]"
          >
            <div>
              <span className="font-medium">Version {v.versionNumber}</span>
              <span className="ml-2 text-xs px-2 py-0.5 bg-gray-100 rounded">
                {v.origin}
              </span>
              {v.changeSummary && (
                <span className="ml-2 text-sm text-gray-600">
                  — {v.changeSummary}
                </span>
              )}
              <div className="text-xs text-gray-400 mt-1">
                {new Date(v.createdAt).toLocaleString()}
              </div>
            </div>
            <button
              onClick={() => handleRestore(v.id)}
              disabled={restoring === v.id}
              className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50"
            >
              {restoring === v.id ? "Restoring..." : "Restore"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
