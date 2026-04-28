"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ENTITY_TYPES } from "@/types";

export default function NewWikiPage() {
  const router = useRouter();
  const [entityName, setEntityName] = useState("");
  const [entityType, setEntityType] = useState("character");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entityName.trim()) {
      setError("Entity name is required");
      return;
    }

    setCreating(true);
    setError(null);

    try {
      const res = await fetch("/api/pages/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entityName: entityName.trim(), entityType }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 409 && data.slug) {
          // Page exists, redirect to it
          router.push(`/wiki/${data.slug}`);
          return;
        }
        throw new Error(data.error || "Failed to create page");
      }

      // Redirect to edit the new page
      router.push(`/wiki/${data.slug}/edit`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create page");
      setCreating(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Create New Page</h1>
        <Link
          href="/wiki"
          className="text-sm text-gray-500 hover:text-gray-700 no-underline"
        >
          Cancel
        </Link>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 p-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleCreate} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Entity Name
          </label>
          <input
            type="text"
            value={entityName}
            onChange={(e) => setEntityName(e.target.value)}
            placeholder="e.g., Catherine Stormborn"
            className="w-full px-3 py-2 border border-[var(--color-wiki-border)] rounded text-sm"
            autoFocus
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Entity Type
          </label>
          <select
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            className="w-full px-3 py-2 border border-[var(--color-wiki-border)] rounded text-sm capitalize"
          >
            {ENTITY_TYPES.map((t) => (
              <option key={t} value={t} className="capitalize">
                {t}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-1">
            The template sections will be customized based on the entity type.
            For example, characters get Relationships and Abilities sections,
            while locations get Geography and Culture sections.
          </p>
        </div>

        <button
          type="submit"
          disabled={creating || !entityName.trim()}
          className="w-full px-4 py-2 bg-[var(--color-wiki-accent)] text-white rounded text-sm hover:bg-[var(--color-wiki-accent-hover)] disabled:opacity-50"
        >
          {creating ? "Creating..." : "Create Page"}
        </button>
      </form>
    </div>
  );
}
