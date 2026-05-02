"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";

const MDEditor = dynamic(() => import("@uiw/react-md-editor"), { ssr: false });

export default function EditPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  const [content, setContent] = useState("");
  const [entityName, setEntityName] = useState("");
  const [changeSummary, setChangeSummary] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);

  // Image upload state
  const [uploading, setUploading] = useState(false);
  const [imageCaption, setImageCaption] = useState("");
  const [isPrimaryImage, setIsPrimaryImage] = useState(false);

  useEffect(() => {
    fetch(`/api/pages/${slug}`)
      .then((r) => {
        if (!r.ok) throw new Error("Page not found");
        return r.json();
      })
      .then((data) => {
        setContent(data.contentMarkdown);
        setEntityName(data.entityName);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [slug]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/pages/${slug}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content_markdown: content,
          change_summary: changeSummary || undefined,
        }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Save failed");
      }
      router.push(`/wiki/${slug}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
      setSaving(false);
    }
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("pageSlug", slug);
    formData.append("caption", imageCaption);
    formData.append("isPrimary", String(isPrimaryImage));

    try {
      const res = await fetch("/api/images", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      // Insert image reference into markdown
      const imgMd = `\n![${data.altText || file.name}](${data.url})\n`;
      setContent((prev) => prev + imgMd);
      setImageCaption("");
      setIsPrimaryImage(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  if (loading) return <p className="text-gray-500">Loading editor...</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Editing: {entityName}</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowHelp(!showHelp)}
            className="text-sm text-gray-500 hover:text-gray-700 cursor-pointer px-2 py-1 border border-gray-300 rounded"
          >
            {showHelp ? "Hide Help" : "Formatting Help"}
          </button>
          <Link
            href={`/wiki/${slug}`}
            className="text-sm text-gray-500 hover:text-gray-700 no-underline px-2 py-1"
          >
            Cancel
          </Link>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 p-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {/* Formatting help panel */}
      {showHelp && (
        <div className="bg-blue-50 border border-blue-200 rounded p-4 mb-4 text-sm">
          <h3 className="font-semibold mb-2">Formatting Guide</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h4 className="font-medium text-gray-700 mb-1">Wiki Links</h4>
              <p className="text-gray-600 mb-1">
                Link to other wiki pages using double brackets:
              </p>
              <code className="bg-white px-2 py-1 rounded text-xs block">
                {"[[Catherine Stormborn]]"}
              </code>
              <p className="text-gray-500 text-xs mt-1">
                Only links to existing pages will be clickable. Non-existent
                pages appear as plain text.
              </p>
            </div>
            <div>
              <h4 className="font-medium text-gray-700 mb-1">Citations</h4>
              <p className="text-gray-600 mb-1">
                Add footnote citations with:
              </p>
              <code className="bg-white px-2 py-1 rounded text-xs block">
                {"Some fact. [^1]"}
              </code>
              <p className="text-gray-600 mt-1 mb-1">
                Define references at the bottom:
              </p>
              <code className="bg-white px-2 py-1 rounded text-xs block">
                {"[^1]: **Source.docx**, §Heading — \"quote\""}
              </code>
            </div>
            <div>
              <h4 className="font-medium text-gray-700 mb-1">Headings</h4>
              <code className="bg-white px-2 py-1 rounded text-xs block">
                {"## Section Heading"}
              </code>
            </div>
            <div>
              <h4 className="font-medium text-gray-700 mb-1">Emphasis</h4>
              <code className="bg-white px-2 py-1 rounded text-xs block">
                {"**bold** and *italic*"}
              </code>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-3">
            Full documentation:{" "}
            <a
              href="https://github.com/aditya-kumaran/spirits-wiki/blob/main/docs/EDITING.md"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-500 underline"
            >
              docs/EDITING.md
            </a>
          </p>
        </div>
      )}

      {/* Markdown Editor */}
      <div data-color-mode="light" className="mb-4">
        <MDEditor
          value={content}
          onChange={(val) => setContent(val || "")}
          height={500}
          preview="edit"
        />
      </div>

      {/* Image Upload Section */}
      <div className="bg-white border border-[var(--color-wiki-border)] rounded p-4 mb-4">
        <h3 className="text-sm font-semibold mb-2">Upload Image</h3>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Image file</label>
            <input
              type="file"
              accept="image/*"
              onChange={handleImageUpload}
              disabled={uploading}
              className="text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Caption</label>
            <input
              type="text"
              value={imageCaption}
              onChange={(e) => setImageCaption(e.target.value)}
              placeholder="Image caption..."
              className="px-2 py-1 border border-gray-300 rounded text-sm"
            />
          </div>
          <div className="flex items-center gap-1">
            <input
              type="checkbox"
              id="isPrimary"
              checked={isPrimaryImage}
              onChange={(e) => setIsPrimaryImage(e.target.checked)}
            />
            <label htmlFor="isPrimary" className="text-xs text-gray-600">
              Primary (infobox)
            </label>
          </div>
          {uploading && <span className="text-xs text-gray-500">Uploading...</span>}
        </div>
      </div>

      {/* Save controls */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={changeSummary}
          onChange={(e) => setChangeSummary(e.target.value)}
          placeholder="Change summary (optional)..."
          className="flex-1 px-3 py-2 border border-[var(--color-wiki-border)] rounded text-sm"
        />
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-[var(--color-wiki-accent)] text-white rounded text-sm hover:bg-[var(--color-wiki-accent-hover)] disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save Page"}
        </button>
      </div>
    </div>
  );
}
