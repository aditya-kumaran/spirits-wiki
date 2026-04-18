"use client";

import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { WikiPage } from "@/types";

export function WikiPageView({ page }: { page: WikiPage }) {
  const primaryImage = page.images?.find((img) => img.isPrimary);
  const otherImages = page.images?.filter((img) => !img.isPrimary) || [];

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
      {(primaryImage || otherImages.length > 0 || page.entityType !== "other") && (
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
                {page.crossLinksFrom.slice(0, 5).map((link) => (
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
      )}

      {/* Main content */}
      <div className="wiki-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {page.contentMarkdown}
        </ReactMarkdown>
      </div>

      {/* Additional images gallery */}
      {otherImages.length > 0 && (
        <div className="mt-6 clear-both">
          <h2 className="text-xl font-semibold border-b border-[var(--color-wiki-heading-border)] pb-1 mb-3">
            Gallery
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {otherImages.map((img) => (
              <div
                key={img.id}
                className="border border-[var(--color-wiki-border)] rounded overflow-hidden bg-white"
              >
                <img
                  src={img.url}
                  alt={img.altText || img.filename}
                  className="w-full h-48 object-cover"
                />
                {img.caption && (
                  <div className="p-2 text-xs text-gray-600">{img.caption}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Source chunks info */}
      {page.sourceBlocks && (page.sourceBlocks as unknown[]).length > 0 && (
        <div className="mt-6 clear-both text-xs text-gray-400 border-t border-gray-200 pt-3">
          Content sourced from {(page.sourceBlocks as unknown[]).length} text
          block(s) across source documents.
        </div>
      )}
    </div>
  );
}
