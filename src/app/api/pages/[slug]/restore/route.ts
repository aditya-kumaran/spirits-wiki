import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function POST(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const { slug } = params;

  try {
    const { version_id } = await request.json();

    if (!version_id) {
      return NextResponse.json(
        { error: "version_id is required" },
        { status: 400 }
      );
    }

    const result = await prisma.$transaction(async (tx) => {
      const targetVersion = await tx.version.findUnique({
        where: { id: version_id },
      });

      if (!targetVersion) {
        throw new Error("Version not found");
      }

      const currentPage = await tx.page.findUnique({ where: { slug } });

      if (!currentPage || targetVersion.pageId !== currentPage.id) {
        throw new Error("Version does not belong to this page");
      }

      const newVersionNumber = currentPage.versionNumber + 1;

      await tx.version.create({
        data: {
          pageId: currentPage.id,
          versionNumber: newVersionNumber,
          contentMarkdown: targetVersion.contentMarkdown,
          sourceBlocks: targetVersion.sourceBlocks ?? [],
          origin: "restore",
          changeSummary: `Restored from version ${targetVersion.versionNumber}`,
        },
      });

      const updatedPage = await tx.page.update({
        where: { slug },
        data: {
          contentMarkdown: targetVersion.contentMarkdown,
          sourceBlocks: targetVersion.sourceBlocks ?? undefined,
          versionNumber: newVersionNumber,
          origin: "restore",
          lastModified: new Date(),
        },
      });

      return updatedPage;
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error("Failed to restore version:", error);
    return NextResponse.json(
      { error: "Failed to restore version" },
      { status: 500 }
    );
  }
}
