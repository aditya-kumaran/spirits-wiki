import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const entityType = searchParams.get("type");
  const search = searchParams.get("q");
  const nameOnly = searchParams.get("nameOnly") === "true";
  const page = parseInt(searchParams.get("page") || "1");
  const limit = parseInt(searchParams.get("limit") || "50");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const where: any = {};
  if (entityType) where.entityType = entityType;
  if (search) {
    if (nameOnly) {
      where.entityName = { contains: search, mode: "insensitive" };
    } else {
      where.OR = [
        { entityName: { contains: search, mode: "insensitive" } },
        { contentMarkdown: { contains: search, mode: "insensitive" } },
      ];
    }
  }

  try {
    const [pages, total] = await Promise.all([
      prisma.page.findMany({
        where,
        select: {
          slug: true,
          entityName: true,
          entityType: true,
          lastModified: true,
          versionNumber: true,
          origin: true,
          conflictStatus: true,
        },
        orderBy: { entityName: "asc" },
        skip: (page - 1) * limit,
        take: limit,
      }),
      prisma.page.count({ where }),
    ]);

    return NextResponse.json({ pages, total, page, limit });
  } catch (error) {
    console.error("Failed to list pages:", error);
    return NextResponse.json({ pages: [], total: 0, page, limit });
  }
}
