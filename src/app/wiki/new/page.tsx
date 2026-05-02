"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ENTITY_TYPES } from "@/types";

const CHARACTER_FIELDS = [
  { key: "spirit", label: "Spirit", placeholder: "e.g., Fox" },
  { key: "aura", label: "Aura", placeholder: "e.g., Mauve" },
  { key: "inspiration", label: "Inspiration", placeholder: "e.g., Loki x Scar (Lion King)" },
  { key: "age", label: "Age", placeholder: "e.g., 24" },
  { key: "powerSet", label: "Power Set", placeholder: "e.g., Telekinesis" },
  { key: "homeSystem", label: "Home System", placeholder: "e.g., Istron" },
  { key: "language", label: "Language", placeholder: "e.g., Urdu/Hindi" },
];

const APPEARANCE_FIELDS = [
  { key: "eyes", label: "Eyes", placeholder: "Eye color/description" },
  { key: "hair", label: "Hair", placeholder: "Hair color/style" },
  { key: "build", label: "Build", placeholder: "Body type" },
  { key: "style", label: "Style", placeholder: "Clothing/fashion style" },
];

export default function NewWikiPage() {
  const router = useRouter();
  const [entityName, setEntityName] = useState("");
  const [entityType, setEntityType] = useState("character");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Character metadata fields
  const [charFields, setCharFields] = useState<Record<string, string>>({});
  const [appearanceFields, setAppearanceFields] = useState<Record<string, string>>({});

  const updateCharField = (key: string, value: string) => {
    setCharFields((prev) => ({ ...prev, [key]: value }));
  };

  const updateAppearanceField = (key: string, value: string) => {
    setAppearanceFields((prev) => ({ ...prev, [key]: value }));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entityName.trim()) {
      setError("Entity name is required");
      return;
    }

    setCreating(true);
    setError(null);

    // Build metadata for characters
    const metadata: Record<string, unknown> = {};
    if (entityType === "character") {
      for (const f of CHARACTER_FIELDS) {
        if (charFields[f.key]) metadata[f.key] = charFields[f.key];
      }
      const appearance: Record<string, string> = {};
      for (const f of APPEARANCE_FIELDS) {
        if (appearanceFields[f.key]) appearance[f.key] = appearanceFields[f.key];
      }
      if (Object.keys(appearance).length > 0) {
        metadata.appearance = appearance;
      }
    }

    try {
      const res = await fetch("/api/pages/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entityName: entityName.trim(),
          entityType,
          metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 409 && data.slug) {
          router.push(`/wiki/${data.slug}`);
          return;
        }
        throw new Error(data.error || "Failed to create page");
      }

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
            placeholder="e.g., Ensa Shahzad"
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
            The template and infobox fields will be customized based on entity type.
          </p>
        </div>

        {/* Character-specific metadata fields */}
        {entityType === "character" && (
          <div className="border border-[var(--color-wiki-border)] rounded p-4 bg-white space-y-3">
            <h3 className="text-sm font-semibold text-gray-700">Character Details</h3>
            <p className="text-xs text-gray-500">
              These fields populate the infobox sidebar. All fields are optional.
            </p>

            {CHARACTER_FIELDS.map((f) => (
              <div key={f.key} className="flex items-center gap-2">
                <label className="text-xs text-gray-600 w-24 shrink-0">{f.label}</label>
                <input
                  type="text"
                  value={charFields[f.key] || ""}
                  onChange={(e) => updateCharField(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm"
                />
              </div>
            ))}

            <h4 className="text-xs font-semibold text-gray-600 mt-3">Appearance</h4>
            {APPEARANCE_FIELDS.map((f) => (
              <div key={f.key} className="flex items-center gap-2">
                <label className="text-xs text-gray-600 w-24 shrink-0">{f.label}</label>
                <input
                  type="text"
                  value={appearanceFields[f.key] || ""}
                  onChange={(e) => updateAppearanceField(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm"
                />
              </div>
            ))}
          </div>
        )}

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
