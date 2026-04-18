import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const { slug } = params;
  const { searchParams } = new URL(request.url);
  const versionId = searchParams.get("id");

  try {
    // If a specific version ID is requested, return its full content
    if (versionId) {
      const version = await prisma.version.findUnique({
        where: { id: versionId },
        include: { page: { select: { slug: true } } },
      });
      if (!version || version.page.slug !== slug) {
        return NextResponse.json({ error: "Version not found" }, { status: 404 });
      }
      return NextResponse.json(version);
    }

    // Otherwise return version list (without full content)
    const page = await prisma.page.findUnique({
      where: { slug },
      select: { id: true },
    });

    if (!page) {
      return NextResponse.json({ error: "Page not found" }, { status: 404 });
    }

    const versions = await prisma.version.findMany({
      where: { pageId: page.id },
      orderBy: { versionNumber: "desc" },
      select: {
        id: true,
        versionNumber: true,
        origin: true,
        createdAt: true,
        changeSummary: true,
      },
    });

    return NextResponse.json(versions);
  } catch (error) {
    console.error("Failed to get versions:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
