"use client";

import { useEffect, useState } from "react";

export default function AdminPage() {
  const [indexStatus, setIndexStatus] = useState<{
    isStale: boolean;
    lastBuilt: string | null;
    editsSinceBuild: number;
    lastBuildStats: {
      chunksIndexed: number;
      pagesIndexed: number;
      durationSeconds: number;
      embeddingModel: string;
    } | null;
  } | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    fetch("/api/index-status")
      .then((r) => r.json())
      .then(setIndexStatus)
      .catch(() => {});
  }, []);

  const handleExport = async (format: string) => {
    setExporting(true);
    try {
      const res = await fetch(`/api/export?format=${format}`);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `spirits-wiki-export-${format}-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Admin</h1>

      {/* Index Status */}
      <div className="bg-white border border-[var(--color-wiki-border)] rounded p-4 mb-6">
        <h2 className="text-lg font-semibold mb-3">Q&A Index Status</h2>
        {indexStatus ? (
          <div>
            <div
              className={
                indexStatus.isStale ? "staleness-warning mb-3" : "staleness-ok mb-3"
              }
            >
              {indexStatus.isStale ? (
                <>
                  Index is <strong>stale</strong>.
                  {indexStatus.lastBuilt
                    ? ` Last built: ${new Date(indexStatus.lastBuilt).toLocaleString()}.`
                    : " Never built."}
                  {indexStatus.editsSinceBuild > 0 &&
                    ` ${indexStatus.editsSinceBuild} page(s) edited since.`}
                </>
              ) : (
                <>
                  Index is <strong>up to date</strong>. Last built:{" "}
                  {new Date(indexStatus.lastBuilt!).toLocaleString()}
                </>
              )}
            </div>

            {indexStatus.lastBuildStats && (
              <div className="text-sm text-gray-600 space-y-1">
                <div>Chunks indexed: {indexStatus.lastBuildStats.chunksIndexed}</div>
                <div>Pages indexed: {indexStatus.lastBuildStats.pagesIndexed}</div>
                <div>
                  Duration: {indexStatus.lastBuildStats.durationSeconds?.toFixed(1)}s
                </div>
                <div>Model: {indexStatus.lastBuildStats.embeddingModel}</div>
              </div>
            )}

            <div className="mt-3 p-3 bg-gray-50 rounded text-sm text-gray-600">
              <strong>To rebuild the Q&A index:</strong>
              <pre className="mt-1 bg-gray-100 p-2 rounded text-xs overflow-auto">
                python scripts/rebuild_index.py
              </pre>
              <p className="mt-1 text-xs text-gray-400">
                This rebuilds the vector index without affecting any wiki content
                or edit history.
              </p>
            </div>
          </div>
        ) : (
          <p className="text-gray-500 text-sm">Loading status...</p>
        )}
      </div>

      {/* Ingestion Instructions */}
      <div className="bg-white border border-[var(--color-wiki-border)] rounded p-4 mb-6">
        <h2 className="text-lg font-semibold mb-3">Document Ingestion</h2>
        <div className="text-sm text-gray-600 space-y-2">
          <p>To ingest new .docx documents into the wiki:</p>
          <pre className="bg-gray-100 p-2 rounded text-xs overflow-auto">
            {`# Ingest all documents in the data directory\npython scripts/ingest.py\n\n# Ingest a specific file\npython scripts/ingest.py --file path/to/document.docx\n\n# After ingestion, rebuild the Q&A index\npython scripts/rebuild_index.py`}
          </pre>
          <p className="text-xs text-gray-400">
            Ingestion will extract entities, create wiki pages with verbatim
            source text, and flag conflicts for pages with manual edits.
          </p>
        </div>
      </div>

      {/* Export */}
      <div className="bg-white border border-[var(--color-wiki-border)] rounded p-4 mb-6">
        <h2 className="text-lg font-semibold mb-3">Backup &amp; Export</h2>
        <div className="flex gap-3">
          <button
            onClick={() => handleExport("json")}
            disabled={exporting}
            className="px-4 py-2 bg-[var(--color-wiki-accent)] text-white rounded text-sm hover:bg-[var(--color-wiki-accent-hover)] disabled:opacity-50"
          >
            {exporting ? "Exporting..." : "Export JSON"}
          </button>
          <button
            onClick={() => handleExport("markdown")}
            disabled={exporting}
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300 disabled:opacity-50"
          >
            Export Markdown
          </button>
        </div>
      </div>
    </div>
  );
}
