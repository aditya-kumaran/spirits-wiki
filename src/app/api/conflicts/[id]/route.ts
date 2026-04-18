import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const pending = await prisma.pendingIngestion.findUnique({
      where: { id: params.id },
      include: {
        page: {
          select: {
            slug: true,
            entityName: true,
            contentMarkdown: true,
          },
        },
      },
    });

    if (!pending) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    return NextResponse.json(pending);
  } catch (error) {
    console.error("Failed to get conflict:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const { resolution, merged_content } = await request.json();

    if (!["accepted", "rejected", "merged"].includes(resolution)) {
      return NextResponse.json(
        { error: "resolution must be 'accepted', 'rejected', or 'merged'" },
        { status: 400 }
      );
    }

    const pending = await prisma.pendingIngestion.findUnique({
      where: { id: params.id },
      include: { page: true },
    });

    if (!pending) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    await prisma.$transaction(async (tx) => {
      if (resolution === "accepted") {
        // Replace page content with incoming
        const newVersion = pending.page.versionNumber + 1;
        await tx.version.create({
          data: {
            pageId: pending.pageId,
            versionNumber: newVersion,
            contentMarkdown: pending.incomingContentMarkdown,
            sourceBlocks: pending.incomingSourceBlocks ?? [],
            origin: "conflict-resolution",
            changeSummary: "Accepted incoming content from re-ingestion",
          },
        });
        await tx.page.update({
          where: { id: pending.pageId },
          data: {
            contentMarkdown: pending.incomingContentMarkdown,
            sourceBlocks: pending.incomingSourceBlocks ?? undefined,
            versionNumber: newVersion,
            origin: "conflict-resolution",
            lastModified: new Date(),
            conflictStatus: "resolved",
          },
        });
      } else if (resolution === "merged" && merged_content) {
        const newVersion = pending.page.versionNumber + 1;
        await tx.version.create({
          data: {
            pageId: pending.pageId,
            versionNumber: newVersion,
            contentMarkdown: merged_content,
            sourceBlocks: pending.page.sourceBlocks ?? [],
            origin: "conflict-resolution",
            changeSummary: "Manually merged with incoming content",
          },
        });
        await tx.page.update({
          where: { id: pending.pageId },
          data: {
            contentMarkdown: merged_content,
            versionNumber: newVersion,
            origin: "conflict-resolution",
            lastModified: new Date(),
            conflictStatus: "resolved",
          },
        });
      } else {
        // Rejected — keep current, just resolve the conflict
        await tx.page.update({
          where: { id: pending.pageId },
          data: { conflictStatus: "resolved" },
        });
      }

      // Mark pending ingestion as resolved
      await tx.pendingIngestion.update({
        where: { id: params.id },
        data: {
          resolved: true,
          resolvedAt: new Date(),
          resolution,
        },
      });
    });

    return NextResponse.json({ success: true, resolution });
  } catch (error) {
    console.error("Failed to resolve conflict:", error);
    return NextResponse.json(
      { error: "Failed to resolve conflict" },
      { status: 500 }
    );
  }
}
