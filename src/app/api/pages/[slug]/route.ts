import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import fs from "fs";
import path from "path";

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
    const { content_markdown, change_summary, metadata: inputMetadata } = body;

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

      // Merge metadata if provided
      const updatedMetadata = inputMetadata
        ? { ...(currentPage.metadata as Record<string, unknown> || {}), ...inputMetadata }
        : undefined;

      // Update the page — immediate, synchronous, durable
      const updatedPage = await tx.page.update({
        where: { slug },
        data: {
          contentMarkdown: content_markdown,
          versionNumber: newVersionNumber,
          origin: "manual-edit",
          lastModified: new Date(),
          ...(updatedMetadata ? { metadata: updatedMetadata } : {}),
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

export async function DELETE(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const { slug } = params;

  try {
    const page = await prisma.page.findUnique({
      where: { slug },
      include: { images: true },
    });

    if (!page) {
      return NextResponse.json({ error: "Page not found" }, { status: 404 });
    }

    // Delete local image files if they exist
    for (const image of page.images) {
      if (image.url.startsWith("/uploads/")) {
        const filePath = path.join(process.cwd(), "public", image.url);
        try {
          if (fs.existsSync(filePath)) {
            fs.unlinkSync(filePath);
          }
        } catch {
          // Non-critical — file may already be gone
        }
      }
    }

    // Delete images and source chunks explicitly (they use SetNull, not Cascade)
    await prisma.image.deleteMany({ where: { pageId: page.id } });
    await prisma.sourceChunk.deleteMany({ where: { pageId: page.id } });

    // Delete the page (cascades to versions, cross_links, pending_ingestions)
    await prisma.page.delete({ where: { slug } });

    return NextResponse.json({ success: true, deleted: page.entityName });
  } catch (error) {
    console.error("Failed to delete page:", error);
    return NextResponse.json(
      { error: "Failed to delete page" },
      { status: 500 }
    );
  }
}
