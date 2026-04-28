"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import type { WikiPage, WikiImage, EntityType } from "@/types";
import { ENTITY_TYPES } from "@/types";

/**
 * Pre-process markdown to convert footnote syntax into proper HTML anchors.
 * - Inline [^N] becomes a clickable superscript linking to #ref-N
 * - Reference [^N]: at line start becomes an anchored numbered entry
 */
function preprocessCitations(md: string): string {
  // Split into lines for reference processing
  const lines = md.split("\n");
  const processedLines: string[] = [];
  let inReferences = false;

  for (const line of lines) {
    if (/^##\s*References?\s*$/i.test(line)) {
      inReferences = true;
      processedLines.push(line);
      continue;
    }

    if (inReferences) {
      // Convert [^N]: into anchored numbered reference
      const refMatch = line.match(/^\[\^(\d+)\]:\s*(.*)/);
      if (refMatch) {
        const num = refMatch[1];
        const rest = refMatch[2];
        processedLines.push(
          `<span id="ref-${num}" class="citation-ref"><strong>${num}.</strong></span> ${rest}`
        );
        continue;
      }
    }

    // In content: convert inline [^N] into clickable superscript links
    // But skip lines that start with [^N]: (definitions)
    if (!line.match(/^\[\^\d+\]:/)) {
      const processed = line.replace(
        /\[\^(\d+)\]/g,
        '<sup><a href="#ref-$1" class="citation-link">[$1]</a></sup>'
      );
      processedLines.push(processed);
    } else {
      processedLines.push(line);
    }
  }

  return processedLines.join("\n");
}

function ImageGallery({
  images,
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

function EntityTypeEditor({
  slug,
  currentType,
  onUpdated,
}: {
  slug: string;
  currentType: string;
  onUpdated: (newType: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState(currentType);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (selected === currentType) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`/api/pages/${slug}/type`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entityType: selected }),
      });
      if (res.ok) {
        onUpdated(selected);
        setEditing(false);
      }
    } catch {
      // silently fail
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="px-2 py-0.5 bg-gray-100 rounded capitalize text-sm text-gray-700 hover:bg-gray-200 cursor-pointer"
        title="Click to change entity type"
      >
        {currentType}
      </button>
    );
  }

  return (
    <span className="inline-flex items-center gap-1">
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="px-2 py-0.5 border border-gray-300 rounded text-sm capitalize"
      >
        {ENTITY_TYPES.map((t) => (
          <option key={t} value={t} className="capitalize">
            {t}
          </option>
        ))}
      </select>
      <button
        onClick={handleSave}
        disabled={saving}
        className="px-2 py-0.5 bg-[var(--color-wiki-accent)] text-white rounded text-xs hover:bg-[var(--color-wiki-accent-hover)] disabled:opacity-50"
      >
        {saving ? "..." : "Save"}
      </button>
      <button
        onClick={() => {
          setSelected(currentType);
          setEditing(false);
        }}
        className="px-2 py-0.5 bg-gray-200 text-gray-600 rounded text-xs hover:bg-gray-300"
      >
        Cancel
      </button>
    </span>
  );
}

function InfoboxRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="wiki-infobox-row">
      <div className="wiki-infobox-label">{label}</div>
      <div className="wiki-infobox-value">{value}</div>
    </div>
  );
}

export function WikiPageView({ page: initialPage }: { page: WikiPage }) {
  const [page, setPage] = useState(initialPage);
  const [validSlugs, setValidSlugs] = useState<Record<string, string>>({});

  const primaryImage = page.images?.find((img) => img.isPrimary);
  const allImages = page.images || [];
  const meta = (page.metadata && typeof page.metadata === "object" && Object.keys(page.metadata).length > 0)
    ? page.metadata as import("@/types").CharacterMetadata
    : null;

  // Fetch all valid page slugs for wiki link validation
  useEffect(() => {
    fetch("/api/pages/slugs")
      .then((r) => r.json())
      .then((data) => setValidSlugs(data))
      .catch(() => {});
  }, []);

  const refreshPage = useCallback(async () => {
    try {
      const res = await fetch(`/api/pages/${page.slug}`);
      if (res.ok) {
        const data = await res.json();
        setPage(data);
      }
    } catch {
      // silently fail refresh
    }
  }, [page.slug]);

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

  const handleTypeUpdated = (newType: string) => {
    setPage((prev) => ({ ...prev, entityType: newType }));
  };

  // Pre-process markdown for proper citation rendering
  const processedMarkdown = preprocessCitations(page.contentMarkdown);

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
        <EntityTypeEditor
          slug={page.slug}
          currentType={page.entityType}
          onUpdated={handleTypeUpdated}
        />
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

        {/* Character-specific metadata fields */}
        {page.entityType === "character" && meta && (
          <>
            {meta.spirit && (
              <InfoboxRow label="Spirit" value={meta.spirit} />
            )}
            {meta.aura && (
              <InfoboxRow label="Aura" value={meta.aura} />
            )}
            {meta.age && (
              <InfoboxRow label="Age" value={meta.age} />
            )}
            {meta.appearance && (
              <>
                {meta.appearance.eyes && (
                  <InfoboxRow label="Eyes" value={meta.appearance.eyes} />
                )}
                {meta.appearance.hair && (
                  <InfoboxRow label="Hair" value={meta.appearance.hair} />
                )}
                {meta.appearance.build && (
                  <InfoboxRow label="Build" value={meta.appearance.build} />
                )}
                {meta.appearance.style && (
                  <InfoboxRow label="Style" value={meta.appearance.style} />
                )}
              </>
            )}
            {meta.powerSet && (
              <InfoboxRow label="Power Set" value={meta.powerSet} />
            )}
            {meta.homeSystem && (
              <InfoboxRow label="Home System" value={meta.homeSystem} />
            )}
            {meta.language && (
              <InfoboxRow label="Language" value={meta.language} />
            )}
            {meta.inspiration && (
              <InfoboxRow label="Inspiration" value={meta.inspiration} />
            )}
          </>
        )}

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

      {/* Main content — render markdown with citation and wiki link support */}
      <div className="wiki-content">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={{
            // Render wiki cross-links: [[Entity Name]] becomes a link
            p: ({ children, ...props }) => {
              const processed = processWikiLinks(children, validSlugs);
              return <p {...props}>{processed}</p>;
            },
            li: ({ children, ...props }) => {
              const processed = processWikiLinks(children, validSlugs);
              return <li {...props}>{processed}</li>;
            },
            // Style citation links
            a: ({ href, children, ...props }) => {
              if (href?.startsWith("#ref-")) {
                return (
                  <a
                    href={href}
                    className="citation-link text-[var(--color-wiki-link)] no-underline hover:underline"
                    {...props}
                  >
                    {children}
                  </a>
                );
              }
              return (
                <a href={href} {...props}>
                  {children}
                </a>
              );
            },
          }}
        >
          {processedMarkdown}
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
 * Only creates links for pages that actually exist in the database.
 */
function processWikiLinks(
  children: React.ReactNode,
  validSlugs: Record<string, string>
): React.ReactNode {
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
        .replace(/['"\u2019\u201C\u201D]/g, "")
        .replace(/[^a-z0-9 -]/g, "")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 100);

      // Only create a link if the page actually exists
      if (slug in validSlugs) {
        parts.push(
          <Link
            key={`${slug}-${match.index}`}
            href={`/wiki/${slug}`}
            className="text-[var(--color-wiki-link)] hover:underline"
          >
            {entityName}
          </Link>
        );
      } else {
        // Page doesn't exist — render as plain text
        parts.push(entityName);
      }
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
      <span key={i}>{processWikiLinks(child, validSlugs)}</span>
    ));
  }

  return children;
}
