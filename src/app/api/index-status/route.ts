import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const [latestBuild, latestEdit, latestChunk] = await Promise.all([
      prisma.indexBuildLog.findFirst({
        where: { status: "completed" },
        orderBy: { completedAt: "desc" },
      }),
      prisma.page.findFirst({
        orderBy: { lastModified: "desc" },
        select: { lastModified: true },
      }),
      prisma.sourceChunk.findFirst({
        orderBy: { createdAt: "desc" },
        select: { createdAt: true },
      }),
    ]);

    const lastBuilt = latestBuild?.completedAt || null;
    const latestChange = latestEdit?.lastModified || latestChunk?.createdAt || null;

    const isStale = lastBuilt && latestChange
      ? latestChange > lastBuilt
      : !lastBuilt && (latestEdit !== null || latestChunk !== null);

    // Count edits since last build
    let editsSinceBuild = 0;
    if (lastBuilt) {
      editsSinceBuild = await prisma.page.count({
        where: { lastModified: { gt: lastBuilt } },
      });
    }

    return NextResponse.json({
      isStale,
      lastBuilt,
      latestChange,
      editsSinceBuild,
      lastBuildStats: latestBuild
        ? {
            chunksIndexed: latestBuild.chunksIndexed,
            pagesIndexed: latestBuild.pagesIndexed,
            durationSeconds: latestBuild.durationSeconds,
            embeddingModel: latestBuild.embeddingModel,
          }
        : null,
    });
  } catch (error) {
    console.error("Failed to get index status:", error);
    return NextResponse.json({
      isStale: true,
      lastBuilt: null,
      latestChange: null,
      editsSinceBuild: 0,
      lastBuildStats: null,
    });
  }
}
