import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const format = searchParams.get("format") || "json";

  try {
    const pages = await prisma.page.findMany({
      include: {
        versions: {
          orderBy: { versionNumber: "asc" },
        },
        images: true,
        crossLinksFrom: {
          include: { targetPage: { select: { slug: true, entityName: true } } },
        },
      },
      orderBy: { entityName: "asc" },
    });

    if (format === "json") {
      return NextResponse.json({
        exportedAt: new Date().toISOString(),
        pageCount: pages.length,
        pages,
      });
    }

    // Markdown format
    const markdownPages = pages.map((page) => ({
      filename: `${page.entityType}/${page.slug}.md`,
      content: `# ${page.entityName}\n\n**Type:** ${page.entityType}\n**Last Modified:** ${page.lastModified.toISOString()}\n**Version:** ${page.versionNumber}\n\n${page.contentMarkdown}`,
    }));

    return NextResponse.json({
      exportedAt: new Date().toISOString(),
      pageCount: markdownPages.length,
      pages: markdownPages,
    });
  } catch (error) {
    console.error("Export failed:", error);
    return NextResponse.json({ error: "Export failed" }, { status: 500 });
  }
}
