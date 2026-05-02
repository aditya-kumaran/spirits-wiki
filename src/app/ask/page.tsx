"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface QASource {
  type: string;
  metadata: Record<string, unknown>;
  excerpt: string;
}

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [sources, setSources] = useState<QASource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [indexStatus, setIndexStatus] = useState<{
    isStale: boolean;
    lastBuilt: string | null;
    editsSinceBuild: number;
  } | null>(null);

  useEffect(() => {
    fetch("/api/index-status")
      .then((r) => r.json())
      .then(setIndexStatus)
      .catch(() => {});
  }, []);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setAnswer(null);
    setSources([]);

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to get answer");
      }

      const data = await res.json();
      setAnswer(data.answer);
      setSources(data.sources || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to get answer");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Ask About the Lore</h1>
      <p className="text-sm text-gray-500 mb-4">
        Ask any question about the Spirits world. The AI will search source
        documents and wiki pages to provide a cited answer.
      </p>

      {/* Index staleness indicator */}
      {indexStatus && (
        <div className={indexStatus.isStale ? "staleness-warning mb-4" : "staleness-ok mb-4"}>
          {indexStatus.isStale ? (
            <>
              Q&amp;A index is stale.
              {indexStatus.lastBuilt
                ? ` Last built: ${new Date(indexStatus.lastBuilt).toLocaleString()}.`
                : " Index has never been built."}
              {indexStatus.editsSinceBuild > 0 &&
                ` ${indexStatus.editsSinceBuild} page(s) edited since last build.`}
              {" "}Changes will not appear in Q&amp;A answers until re-indexed.
            </>
          ) : (
            <>Q&amp;A index is up to date. Last built: {new Date(indexStatus.lastBuilt!).toLocaleString()}</>
          )}
        </div>
      )}

      <form onSubmit={handleAsk} className="mb-6">
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g., Who are the main characters? What happened during the war?"
            className="flex-1 px-3 py-2 border border-[var(--color-wiki-border)] rounded text-sm"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="px-4 py-2 bg-[var(--color-wiki-accent)] text-white rounded text-sm hover:bg-[var(--color-wiki-accent-hover)] disabled:opacity-50"
          >
            {loading ? "Thinking..." : "Ask"}
          </button>
        </div>
      </form>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 p-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {answer && (
        <div className="bg-white border border-[var(--color-wiki-border)] rounded p-4 mb-4">
          <h2 className="text-sm font-semibold text-gray-500 mb-2">Answer</h2>
          <div className="wiki-content prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
          </div>
        </div>
      )}

      {sources.length > 0 && (
        <div className="bg-gray-50 border border-gray-200 rounded p-4">
          <h2 className="text-sm font-semibold text-gray-500 mb-2">
            Sources ({sources.length})
          </h2>
          <div className="space-y-2">
            {sources.map((source, i) => (
              <div key={i} className="text-xs p-2 bg-white rounded border border-gray-200">
                <span className={`px-1.5 py-0.5 rounded text-white text-[10px] mr-2 ${
                  source.type === "source_document" ? "bg-blue-500" : "bg-green-600"
                }`}>
                  {source.type === "source_document" ? "DOC" : "WIKI"}
                </span>
                <span className="text-gray-600">
                  {source.type === "source_document"
                    ? `${(source.metadata as { docFilename?: string }).docFilename}`
                    : `${(source.metadata as { entityName?: string }).entityName}`}
                </span>
                <div className="mt-1 text-gray-400 truncate">{source.excerpt}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
