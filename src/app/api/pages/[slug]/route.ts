import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const { slug } = params;

  try {
    const page = await prisma.page.findUnique({
      where: { slug },
      include: {
        crossLinksFrom: {
          include: { targetPage: { select: { slug: true, entityName: true } } },
        },
        images: {
          orderBy: [{ isPrimary: "desc" }, { sortOrder: "asc" }],
        },
      },
    });

    if (!page) {
      return NextResponse.json({ error: "Page not found" }, { status: 404 });
    }

    return NextResponse.json(page);
  } catch (error) {
    console.error("Failed to get page:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const { slug } = params;

  try {
    const body = await request.json();
    const { content_markdown, change_summary } = body;

    if (!content_markdown || typeof content_markdown !== "string") {
      return NextResponse.json(
        { error: "content_markdown is required" },
        { status: 400 }
      );
    }

    const result = await prisma.$transaction(async (tx) => {
      const currentPage = await tx.page.findUnique({ where: { slug } });

      if (!currentPage) {
        throw new Error("Page not found");
      }

      const newVersionNumber = currentPage.versionNumber + 1;

      // Create version record (snapshot of new state)
      await tx.version.create({
        data: {
          pageId: currentPage.id,
          versionNumber: newVersionNumber,
          contentMarkdown: content_markdown,
          sourceBlocks: currentPage.sourceBlocks ?? [],
          origin: "manual-edit",
          changeSummary: change_summary || null,
        },
      });

      // Update the page — immediate, synchronous, durable
      const updatedPage = await tx.page.update({
        where: { slug },
        data: {
          contentMarkdown: content_markdown,
          versionNumber: newVersionNumber,
          origin: "manual-edit",
          lastModified: new Date(),
        },
      });

      return updatedPage;
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error("Failed to update page:", error);
    return NextResponse.json(
      { error: "Failed to save page" },
      { status: 500 }
    );
  }
}
