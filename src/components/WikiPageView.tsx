"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { WikiPage, WikiImage } from "@/types";

function CitationTooltip({ citation }: { citation: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline">
      <button
        onClick={() => setOpen(!open)}
        className="text-[var(--color-wiki-link)] text-xs align-super cursor-pointer hover:underline ml-0.5"
      >
        [{citation.split("|")[0]}]
      </button>
      {open && (
        <span className="absolute z-50 left-0 top-full mt-1 w-80 bg-white border border-[var(--color-wiki-border)] rounded shadow-lg p-3 text-xs text-gray-700 leading-relaxed">
          <span className="font-semibold block mb-1">Source:</span>
          {citation.split("|").slice(1).join("|")}
          <button
            onClick={() => setOpen(false)}
            className="block mt-2 text-[var(--color-wiki-link)] cursor-pointer"
          >
            Close
          </button>
        </span>
      )}
    </span>
  );
}

function ImageGallery({
  images,
  slug,
  onSetPrimary,
}: {
  images: WikiImage[];
  slug: string;
  onSetPrimary: (id: string) => void;
}) {
  return (
    <div className="mt-6 clear-both">
      <h2 className="text-xl font-semibold border-b border-[var(--color-wiki-heading-border)] pb-1 mb-3">
        Gallery
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {images.map((img) => (
          <div
            key={img.id}
            className="border border-[var(--color-wiki-border)] rounded overflow-hidden bg-white"
          >
            <img
              src={img.url}
              alt={img.altText || img.filename}
              className="w-full h-48 object-cover"
            />
            <div className="p-2">
              {img.caption && (
                <div className="text-xs text-gray-600 mb-1">{img.caption}</div>
              )}
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">
                  {img.isPrimary ? (
                    <span className="text-[var(--color-wiki-success)] font-semibold">
                      Display Image
                    </span>
                  ) : (
                    img.origin
                  )}
                </span>
                {!img.isPrimary && (
                  <button
                    onClick={() => onSetPrimary(img.id)}
                    className="text-xs text-[var(--color-wiki-link)] hover:underline cursor-pointer"
                  >
                    Set as display
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ImageUploadWidget({
  slug,
  onUploaded,
}: {
  slug: string;
  onUploaded: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [caption, setCaption] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("pageSlug", slug);
    formData.append("caption", caption);
    formData.append("isPrimary", String(isPrimary));

    try {
      const res = await fetch("/api/images", { method: "POST", body: formData });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Upload failed");
      }
      setCaption("");
      setIsPrimary(false);
      if (fileRef.current) fileRef.current.value = "";
      onUploaded();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="mt-4 bg-white border border-[var(--color-wiki-border)] rounded p-4">
      <h3 className="text-sm font-semibold mb-2">Upload Image</h3>
      {error && (
        <div className="text-xs text-red-600 mb-2">{error}</div>
      )}
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Image file</label>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            onChange={handleUpload}
            disabled={uploading}
            className="text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Caption</label>
          <input
            type="text"
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            placeholder="Image caption..."
            className="px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div className="flex items-center gap-1">
          <input
            type="checkbox"
            id="isPrimaryUpload"
            checked={isPrimary}
            onChange={(e) => setIsPrimary(e.target.checked)}
          />
          <label htmlFor="isPrimaryUpload" className="text-xs text-gray-600">
            Set as display image
          </label>
        </div>
        {uploading && <span className="text-xs text-gray-500">Uploading...</span>}
      </div>
    </div>
  );
}

export function WikiPageView({ page: initialPage }: { page: WikiPage }) {
  const [page, setPage] = useState(initialPage);

  const primaryImage = page.images?.find((img) => img.isPrimary);
  const allImages = page.images || [];

  const refreshPage = async () => {
    try {
      const res = await fetch(`/api/pages/${page.slug}`);
      if (res.ok) {
        const data = await res.json();
        setPage(data);
      }
    } catch {
      // silently fail refresh
    }
  };

  const handleSetPrimary = async (imageId: string) => {
    try {
      const res = await fetch(`/api/images/${imageId}/primary`, {
        method: "POST",
      });
      if (res.ok) {
        refreshPage();
      }
    } catch {
      // silently fail
    }
  };

  return (
    <div>
      {/* Conflict banner */}
      {page.conflictStatus === "pending" && (
        <div className="conflict-banner">
          <strong>Conflict detected:</strong> New source material has been found
          for this entity. Manual edits exist on this page.{" "}
          <Link
            href="/conflicts"
            className="text-[var(--color-wiki-link)] underline"
          >
            Review and resolve
          </Link>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-3xl font-bold">{page.entityName}</h1>
        <div className="flex gap-2">
          <Link
            href={`/wiki/${page.slug}/edit`}
            className="px-3 py-1.5 bg-[var(--color-wiki-accent)] text-white rounded text-sm no-underline hover:bg-[var(--color-wiki-accent-hover)]"
          >
            Edit
          </Link>
          <Link
            href={`/wiki/${page.slug}/history`}
            className="px-3 py-1.5 bg-gray-200 text-gray-700 rounded text-sm no-underline hover:bg-gray-300"
          >
            History
          </Link>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-4 text-sm text-gray-500">
        <span className="px-2 py-0.5 bg-gray-100 rounded capitalize">
          {page.entityType}
        </span>
        <span>
          Version {page.versionNumber} &middot; Last modified{" "}
          {new Date(page.lastModified).toLocaleString()}
        </span>
        <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
          {page.origin}
        </span>
      </div>

      {/* Infobox (Fandom-style) */}
      <div className="wiki-infobox">
        <div className="wiki-infobox-header">{page.entityName}</div>
        {primaryImage && (
          <div className="wiki-infobox-image">
            <img
              src={primaryImage.url}
              alt={primaryImage.altText || page.entityName}
            />
            {primaryImage.caption && (
              <div className="text-xs text-gray-500 mt-1 italic">
                {primaryImage.caption}
              </div>
            )}
          </div>
        )}
        <div className="wiki-infobox-row">
          <div className="wiki-infobox-label">Type</div>
          <div className="wiki-infobox-value capitalize">{page.entityType}</div>
        </div>
        <div className="wiki-infobox-row">
          <div className="wiki-infobox-label">Origin</div>
          <div className="wiki-infobox-value">{page.origin}</div>
        </div>
        <div className="wiki-infobox-row">
          <div className="wiki-infobox-label">Version</div>
          <div className="wiki-infobox-value">{page.versionNumber}</div>
        </div>
        {page.crossLinksFrom && page.crossLinksFrom.length > 0 && (
          <div className="wiki-infobox-row">
            <div className="wiki-infobox-label">Related</div>
            <div className="wiki-infobox-value">
              {page.crossLinksFrom.map((link) => (
                <div key={link.id}>
                  <Link
                    href={`/wiki/${link.targetPage.slug}`}
                    className="text-[var(--color-wiki-link)] text-xs hover:underline"
                  >
                    {link.targetPage.entityName}
                  </Link>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Main content — render markdown with citation support */}
      <div className="wiki-content">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Render wiki cross-links: [[Entity Name]] becomes a link
            p: ({ children, ...props }) => {
              const processed = processWikiLinks(children);
              return <p {...props}>{processed}</p>;
            },
          }}
        >
          {page.contentMarkdown}
        </ReactMarkdown>
      </div>

      {/* Image gallery */}
      {allImages.length > 0 && (
        <ImageGallery
          images={allImages}
          slug={page.slug}
          onSetPrimary={handleSetPrimary}
        />
      )}

      {/* Image upload */}
      <ImageUploadWidget slug={page.slug} onUploaded={refreshPage} />

      {/* Source citations reference */}
      {page.sourceBlocks && (page.sourceBlocks as unknown[]).length > 0 && (
        <div className="mt-6 clear-both text-xs text-gray-400 border-t border-gray-200 pt-3">
          Content sourced from {(page.sourceBlocks as unknown[]).length} text
          block(s) across source documents.
        </div>
      )}
    </div>
  );
}

/**
 * Process children to find [[wiki links]] and turn them into actual links.
 */
function processWikiLinks(children: React.ReactNode): React.ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    const regex = /\[\[([^\]]+)\]\]/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(children)) !== null) {
      if (match.index > lastIndex) {
        parts.push(children.slice(lastIndex, match.index));
      }
      const entityName = match[1];
      const slug = entityName
        .toLowerCase()
        .replace(/['"'""]/g, "")
        .replace(/[^a-z0-9 -]/g, "")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 100);
      parts.push(
        <Link
          key={`${slug}-${match.index}`}
          href={`/wiki/${slug}`}
          className="text-[var(--color-wiki-link)] hover:underline"
        >
          {entityName}
        </Link>
      );
      lastIndex = regex.lastIndex;
    }

    if (parts.length === 0) return children;
    if (lastIndex < children.length) {
      parts.push(children.slice(lastIndex));
    }
    return <>{parts}</>;
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => (
      <span key={i}>{processWikiLinks(child)}</span>
    ));
  }

  return children;
}
