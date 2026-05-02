"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import type { WikiPage } from "@/types";
import { WikiPageView } from "@/components/WikiPageView";

export default function WikiPageRoute() {
  const params = useParams();
  const slug = params.slug as string;
  const [page, setPage] = useState<WikiPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/pages/${slug}`)
      .then((r) => {
        if (!r.ok) throw new Error("Page not found");
        return r.json();
      })
      .then((data) => {
        setPage(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [slug]);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error || !page)
    return (
      <div>
        <p className="text-red-600">Page not found: {slug}</p>
        <Link href="/wiki" className="text-[var(--color-wiki-link)]">
          Back to all pages
        </Link>
      </div>
    );

  return <WikiPageView page={page} />;
}
