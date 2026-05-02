import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const pages = await prisma.page.findMany({
      select: { slug: true, entityName: true },
    });
    const slugMap: Record<string, string> = {};
    for (const p of pages) {
      slugMap[p.slug] = p.entityName;
    }
    return NextResponse.json(slugMap);
  } catch {
    return NextResponse.json({});
  }
}
