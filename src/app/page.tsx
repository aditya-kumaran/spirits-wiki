import Link from "next/link";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let stats = { pages: 0, characters: 0, locations: 0, conflicts: 0 };
  try {
    const [pages, characters, locations, conflicts] = await Promise.all([
      prisma.page.count(),
      prisma.page.count({ where: { entityType: "character" } }),
      prisma.page.count({ where: { entityType: "location" } }),
      prisma.page.count({ where: { conflictStatus: "pending" } }),
    ]);
    stats = { pages, characters, locations, conflicts };
  } catch {
    // DB not yet initialized
  }

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">Spirits Wiki</h1>
      <p className="text-gray-600 mb-6">
        Private lore reference for the Spirits fictional world.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Pages" value={stats.pages} />
        <StatCard label="Characters" value={stats.characters} />
        <StatCard label="Locations" value={stats.locations} />
        <StatCard label="Conflicts" value={stats.conflicts} color={stats.conflicts > 0 ? "warning" : undefined} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-5 rounded border border-[var(--color-wiki-border)]">
          <h2 className="text-lg font-semibold mb-3">Quick Links</h2>
          <ul className="space-y-2">
            <li>
              <Link href="/wiki" className="text-[var(--color-wiki-link)] hover:underline">
                Browse all wiki pages
              </Link>
            </li>
            <li>
              <Link href="/ask" className="text-[var(--color-wiki-link)] hover:underline">
                Ask a question about the lore
              </Link>
            </li>
            <li>
              <Link href="/wiki?type=character" className="text-[var(--color-wiki-link)] hover:underline">
                View all characters
              </Link>
            </li>
            <li>
              <Link href="/wiki?type=location" className="text-[var(--color-wiki-link)] hover:underline">
                View all locations
              </Link>
            </li>
          </ul>
        </div>
        <div className="bg-white p-5 rounded border border-[var(--color-wiki-border)]">
          <h2 className="text-lg font-semibold mb-3">About This Wiki</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            This wiki is automatically generated from the Spirits source
            documents. All content on wiki pages is extracted verbatim from
            the original .docx files. Pages can be manually edited, with
            full version history and conflict resolution when new documents
            are ingested.
          </p>
          <p className="text-sm text-gray-600 leading-relaxed mt-2">
            The Q&amp;A system uses RAG to answer questions by searching across
            both source documents and wiki pages.
          </p>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: "warning";
}) {
  return (
    <div
      className={`p-4 rounded border ${
        color === "warning"
          ? "bg-yellow-50 border-yellow-300"
          : "bg-white border-[var(--color-wiki-border)]"
      }`}
    >
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm text-gray-500">{label}</div>
    </div>
  );
}
