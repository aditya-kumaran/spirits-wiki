import { NextRequest, NextResponse } from "next/server";
import { put } from "@vercel/blob";
import { prisma } from "@/lib/db";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;
    const pageSlug = formData.get("pageSlug") as string | null;
    const caption = formData.get("caption") as string | null;
    const isPrimary = formData.get("isPrimary") === "true";

    if (!file) {
      return NextResponse.json({ error: "No file provided" }, { status: 400 });
    }

    // Upload to Vercel Blob
    const blob = await put(`wiki-images/${Date.now()}-${file.name}`, file, {
      access: "public",
    });

    // Find the page if slug provided
    let pageId: string | null = null;
    if (pageSlug) {
      const page = await prisma.page.findUnique({
        where: { slug: pageSlug },
        select: { id: true },
      });
      pageId = page?.id || null;

      // If setting as primary, unset other primaries for this page
      if (isPrimary && pageId) {
        await prisma.image.updateMany({
          where: { pageId, isPrimary: true },
          data: { isPrimary: false },
        });
      }
    }

    const image = await prisma.image.create({
      data: {
        pageId,
        filename: file.name,
        altText: file.name.replace(/\.[^.]+$/, ""),
        caption: caption || null,
        url: blob.url,
        isPrimary,
        origin: "manual-upload",
      },
    });

    return NextResponse.json(image);
  } catch (error) {
    console.error("Image upload failed:", error);
    return NextResponse.json(
      { error: "Failed to upload image" },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const pageSlug = searchParams.get("pageSlug");

  try {
    if (pageSlug) {
      const page = await prisma.page.findUnique({
        where: { slug: pageSlug },
        select: { id: true },
      });
      if (!page) {
        return NextResponse.json({ error: "Page not found" }, { status: 404 });
      }
      const images = await prisma.image.findMany({
        where: { pageId: page.id },
        orderBy: [{ isPrimary: "desc" }, { sortOrder: "asc" }],
      });
      return NextResponse.json(images);
    }

    const images = await prisma.image.findMany({
      orderBy: { createdAt: "desc" },
      take: 50,
    });
    return NextResponse.json(images);
  } catch (error) {
    console.error("Failed to get images:", error);
    return NextResponse.json({ error: "Failed to get images" }, { status: 500 });
  }
}
