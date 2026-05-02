import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/db";

/**
 * POST /api/pages/[slug]/merge
 * Merges the current page (source) INTO a target page.
 * - Appends source content to target content
 * - Moves source chunks, images, and cross-links to target
 * - Merges metadata
 * - Deletes the source page
 *
 * Body: { targetSlug: string }
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const sourceSlug = params.slug;

  try {
    const body = await request.json();
    const { targetSlug } = body;

    if (!targetSlug || typeof targetSlug !== "string") {
      return NextResponse.json(
        { error: "targetSlug is required" },
        { status: 400 }
      );
    }

    if (sourceSlug === targetSlug) {
      return NextResponse.json(
        { error: "Cannot merge a page into itself" },
        { status: 400 }
      );
    }

    const result = await prisma.$transaction(async (tx) => {
      const sourcePage = await tx.page.findUnique({
        where: { slug: sourceSlug },
        include: { images: true },
      });
      const targetPage = await tx.page.findUnique({
        where: { slug: targetSlug },
      });

      if (!sourcePage) {
        throw new Error(`Source page not found: ${sourceSlug}`);
      }
      if (!targetPage) {
        throw new Error(`Target page not found: ${targetSlug}`);
      }

      // 1. Merge content: append source content under a heading
      const mergedContent =
        targetPage.contentMarkdown +
        `\n\n---\n\n## Merged from: ${sourcePage.entityName}\n\n` +
        sourcePage.contentMarkdown;

      // 2. Merge source blocks (JSON arrays)
      const targetBlocks = Array.isArray(targetPage.sourceBlocks)
        ? (targetPage.sourceBlocks as unknown[])
        : [];
      const sourceBlocks = Array.isArray(sourcePage.sourceBlocks)
        ? (sourcePage.sourceBlocks as unknown[])
        : [];
      const mergedBlocks = [...targetBlocks, ...sourceBlocks] as Prisma.InputJsonValue[];

      // 3. Merge metadata
      const targetMeta =
        (targetPage.metadata as Record<string, unknown>) || {};
      const sourceMeta =
        (sourcePage.metadata as Record<string, unknown>) || {};
      // Target takes precedence for conflicting keys
      const mergedMeta = { ...sourceMeta, ...targetMeta } as Prisma.InputJsonObject;

      // 4. Move source chunks to target page
      await tx.sourceChunk.updateMany({
        where: { pageId: sourcePage.id },
        data: { pageId: targetPage.id },
      });

      // 5. Move images to target page
      // If target has no primary image, keep the source's primary; otherwise demote it
      const targetHasPrimary = await tx.image.findFirst({
        where: { pageId: targetPage.id, isPrimary: true },
      });
      for (const img of sourcePage.images) {
        await tx.image.update({
          where: { id: img.id },
          data: {
            pageId: targetPage.id,
            isPrimary: !targetHasPrimary && img.isPrimary,
          },
        });
      }

      // 6. Re-point cross-links from source to target
      // Links where source page is the "from" side
      const outLinks = await tx.crossLink.findMany({
        where: { sourcePageId: sourcePage.id },
      });
      for (const link of outLinks) {
        // Skip self-links and duplicates
        if (link.targetPageId === targetPage.id) {
          await tx.crossLink.delete({ where: { id: link.id } });
          continue;
        }
        // Check if target already has this link
        const existing = await tx.crossLink.findUnique({
          where: {
            sourcePageId_targetPageId: {
              sourcePageId: targetPage.id,
              targetPageId: link.targetPageId,
            },
          },
        });
        if (existing) {
          await tx.crossLink.delete({ where: { id: link.id } });
        } else {
          await tx.crossLink.update({
            where: { id: link.id },
            data: { sourcePageId: targetPage.id },
          });
        }
      }

      // Links where source page is the "to" side
      const inLinks = await tx.crossLink.findMany({
        where: { targetPageId: sourcePage.id },
      });
      for (const link of inLinks) {
        if (link.sourcePageId === targetPage.id) {
          await tx.crossLink.delete({ where: { id: link.id } });
          continue;
        }
        const existing = await tx.crossLink.findUnique({
          where: {
            sourcePageId_targetPageId: {
              sourcePageId: link.sourcePageId,
              targetPageId: targetPage.id,
            },
          },
        });
        if (existing) {
          await tx.crossLink.delete({ where: { id: link.id } });
        } else {
          await tx.crossLink.update({
            where: { id: link.id },
            data: { targetPageId: targetPage.id },
          });
        }
      }

      // 7. Create a version record for the merge
      const newVersion = targetPage.versionNumber + 1;
      await tx.version.create({
        data: {
          pageId: targetPage.id,
          versionNumber: newVersion,
          contentMarkdown: mergedContent,
          sourceBlocks: mergedBlocks,
          origin: "merge",
          changeSummary: `Merged content from "${sourcePage.entityName}"`,
        },
      });

      // 8. Update the target page
      const updated = await tx.page.update({
        where: { slug: targetSlug },
        data: {
          contentMarkdown: mergedContent,
          sourceBlocks: mergedBlocks,
          metadata: mergedMeta,
          versionNumber: newVersion,
          origin: "merge",
          lastModified: new Date(),
        },
      });

      // 9. Delete the source page (cascades versions, pending ingestions)
      await tx.page.delete({ where: { slug: sourceSlug } });

      return {
        targetPage: updated,
        mergedFrom: sourcePage.entityName,
        sourceChunksMoved: sourceBlocks.length,
        imagesMoved: sourcePage.images.length,
      };
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error("Failed to merge pages:", error);
    const message =
      error instanceof Error ? error.message : "Failed to merge pages";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
