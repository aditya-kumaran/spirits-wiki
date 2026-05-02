import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import Groq from "groq-sdk";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

export async function POST(request: NextRequest) {
  try {
    const { question } = await request.json();

    if (!question || typeof question !== "string") {
      return NextResponse.json(
        { error: "question is required" },
        { status: 400 }
      );
    }

    // For now, use full-text search against pages as a simpler retrieval
    // The pgvector-based retrieval is handled by the Python rebuild_index + a
    // dedicated embedding search. This route uses keyword search as a baseline
    // that works without the vector index.
    const pages = await prisma.page.findMany({
      where: {
        OR: [
          { contentMarkdown: { contains: question.split(" ")[0], mode: "insensitive" } },
          { entityName: { contains: question.split(" ")[0], mode: "insensitive" } },
        ],
      },
      select: {
        slug: true,
        entityName: true,
        entityType: true,
        contentMarkdown: true,
        origin: true,
      },
      take: 10,
    });

    // Also search source chunks
    const chunks = await prisma.sourceChunk.findMany({
      where: {
        text: { contains: question.split(" ")[0], mode: "insensitive" },
      },
      select: {
        text: true,
        docFilename: true,
        headingPath: true,
        entityName: true,
        sectionType: true,
      },
      take: 10,
    });

    // Build context for LLM
    const contextParts: string[] = [];

    chunks.forEach((chunk, i) => {
      const heading = chunk.headingPath?.join(" > ") || "N/A";
      contextParts.push(
        `--- Source Document ${i + 1} [${chunk.docFilename}, §${heading}] ---\n${chunk.text.substring(0, 1000)}`
      );
    });

    pages.forEach((page, i) => {
      const editedNote = page.origin === "manual-edit" ? " (manually edited)" : "";
      contextParts.push(
        `--- Wiki Page ${i + 1}: ${page.entityName}${editedNote} ---\n${page.contentMarkdown.substring(0, 1500)}`
      );
    });

    const context = contextParts.join("\n\n");

    // Generate answer with Groq
    const groqApiKey = process.env.GROQ_API_KEY;
    if (!groqApiKey) {
      return NextResponse.json(
        { error: "GROQ_API_KEY not configured" },
        { status: 500 }
      );
    }

    const groq = new Groq({ apiKey: groqApiKey });

    const completion = await groq.chat.completions.create({
      model: "llama-3.3-70b-versatile",
      messages: [
        {
          role: "system",
          content: `You are a lore expert assistant for a fictional world called "Spirits". Answer questions using ONLY the provided context. For every claim, cite the source using the labels provided (e.g., [Source: filename.docx, §Section] or [Wiki: Entity Name]).

If a source is from a wiki page that has been manually edited, note this.
If the context does not contain enough information to answer, say so honestly.
Do not invent or infer information beyond what the context provides.`,
        },
        {
          role: "user",
          content: `Context:\n${context}\n\nQuestion: ${question}`,
        },
      ],
      temperature: 0.3,
      max_tokens: 1500,
    });

    const answer = completion.choices[0]?.message?.content || "Unable to generate answer.";

    // Get index staleness info
    let indexStaleness = { isStale: true, lastBuilt: null as string | null, latestEdit: null as string | null };
    try {
      const latestBuild = await prisma.indexBuildLog.findFirst({
        where: { status: "completed" },
        orderBy: { completedAt: "desc" },
      });
      const latestEdit = await prisma.page.findFirst({
        orderBy: { lastModified: "desc" },
        select: { lastModified: true },
      });
      indexStaleness = {
        isStale: latestBuild?.completedAt && latestEdit?.lastModified
          ? latestEdit.lastModified > latestBuild.completedAt
          : true,
        lastBuilt: latestBuild?.completedAt?.toISOString() || null,
        latestEdit: latestEdit?.lastModified?.toISOString() || null,
      };
    } catch {
      // Index status tables may not exist yet
    }

    return NextResponse.json({
      answer,
      sources: [
        ...chunks.map((c) => ({
          type: "source_document",
          metadata: { docFilename: c.docFilename, headingPath: c.headingPath, entityName: c.entityName },
          excerpt: c.text.substring(0, 200) + "...",
        })),
        ...pages.map((p) => ({
          type: "wiki_page",
          metadata: { slug: p.slug, entityName: p.entityName, origin: p.origin },
          excerpt: p.contentMarkdown.substring(0, 200) + "...",
        })),
      ],
      indexStaleness,
    });
  } catch (error) {
    console.error("Q&A failed:", error);
    return NextResponse.json(
      { error: "Failed to process question" },
      { status: 500 }
    );
  }
}
