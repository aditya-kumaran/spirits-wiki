import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function PUT(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const { slug } = params;

  try {
    const body = await request.json();
    const { entityType } = body;

    if (!entityType || typeof entityType !== "string") {
      return NextResponse.json(
        { error: "entityType is required" },
        { status: 400 }
      );
    }

    const page = await prisma.page.update({
      where: { slug },
      data: { entityType },
    });

    return NextResponse.json(page);
  } catch (error) {
    console.error("Failed to update entity type:", error);
    return NextResponse.json(
      { error: "Failed to update entity type" },
      { status: 500 }
    );
  }
}
