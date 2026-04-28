import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const { id } = params;

  try {
    const image = await prisma.image.findUnique({
      where: { id },
      select: { id: true, pageId: true },
    });

    if (!image) {
      return NextResponse.json({ error: "Image not found" }, { status: 404 });
    }

    if (!image.pageId) {
      return NextResponse.json(
        { error: "Image is not associated with a page" },
        { status: 400 }
      );
    }

    // Unset all other primaries for this page
    await prisma.image.updateMany({
      where: { pageId: image.pageId, isPrimary: true },
      data: { isPrimary: false },
    });

    // Set this one as primary
    const updated = await prisma.image.update({
      where: { id },
      data: { isPrimary: true },
    });

    return NextResponse.json(updated);
  } catch (error) {
    console.error("Failed to set primary image:", error);
    return NextResponse.json(
      { error: "Failed to set primary image" },
      { status: 500 }
    );
  }
}
