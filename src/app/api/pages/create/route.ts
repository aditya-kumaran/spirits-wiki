import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/['"\u2019\u201C\u201D]/g, "")
    .replace(/[^a-z0-9 -]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 100);
}

const ENTITY_TEMPLATES: Record<string, string> = {
  character: `## Overview

A brief description of this character.

## Relationships

Notable relationships with other characters. Include personality traits in the relevant era subsection.

### Part One

Relationships and personality traits during Part One.

### Part Two

Relationships and personality traits during Part Two.

## Abilities

Powers, skills, or notable abilities.

## Plot

Organize plot points by era. Use ### subheadings for each era/age/part.

### Part One

Events during Part One.

### Part Two

Events during Part Two.
`,
  location: `## Overview

A brief description of this location.

## Geography

Physical features and layout.

## History

Organize history by era. Use ### subheadings for each era/age/part.

### Part One

Events during Part One.

### Part Two

Events during Part Two.

## Culture

Cultural significance and customs associated with this location.

## Notable Residents

Important figures associated with this location.
`,
  faction: `## Overview

A brief description of this faction.

## History

Origins and key events.

## Structure

Organization and hierarchy.

## Members

Notable members of this faction.

## Goals

Objectives and motivations.
`,
  event: `## Overview

A brief description of this event.

## Background

Context and causes.

## Timeline

Key moments during the event.

## Aftermath

Consequences and lasting impact.

## Key Figures

Important participants.
`,
  era: `## Overview

A brief description of this era.

## Timeline

Major events during this period.

## Key Figures

Notable individuals of this era.

## Legacy

Lasting impact on the world.
`,
  artifact: `## Overview

A brief description of this artifact.

## History

Origins and key events involving this artifact.

## Properties

Powers, abilities, or notable properties.

## Current Status

Where the artifact is now and who possesses it.
`,
  concept: `## Overview

A brief description of this concept.

## Explanation

Detailed explanation.

## Significance

Why this concept matters in the world.

## Related Topics

Other concepts and entities related to this one.
`,
  species: `## Overview

A brief description of this species.

## Characteristics

Physical and behavioral traits.

## Habitat

Where this species is found.

## Culture

Social structure and customs (if sentient).

## Notable Members

Important individuals of this species.
`,
  other: `## Overview

A brief description.

## Details

Additional information.
`,
};

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { entityName, entityType, metadata: inputMetadata } = body;

    if (!entityName || typeof entityName !== "string") {
      return NextResponse.json(
        { error: "entityName is required" },
        { status: 400 }
      );
    }

    const slug = slugify(entityName.trim());
    if (!slug) {
      return NextResponse.json(
        { error: "Invalid entity name" },
        { status: 400 }
      );
    }

    // Check if page already exists
    const existing = await prisma.page.findUnique({ where: { slug } });
    if (existing) {
      return NextResponse.json(
        { error: "A page with this name already exists", slug },
        { status: 409 }
      );
    }

    const type = entityType || "other";
    const template = ENTITY_TEMPLATES[type] || ENTITY_TEMPLATES.other;

    const page = await prisma.$transaction(async (tx) => {
      const defaultMeta = type === "character" ? {
        spirit: "", aura: "", appearance: { eyes: "", hair: "", build: "", style: "" },
        inspiration: "", age: "", powerSet: "", homeSystem: "", language: "",
      } : {};
      const pageMeta = inputMetadata && typeof inputMetadata === "object"
        ? { ...defaultMeta, ...inputMetadata }
        : defaultMeta;

      const newPage = await tx.page.create({
        data: {
          slug,
          entityName: entityName.trim(),
          entityType: type,
          contentMarkdown: template,
          sourceBlocks: [],
          metadata: pageMeta,
          versionNumber: 1,
          origin: "manual-create",
        },
      });

      await tx.version.create({
        data: {
          pageId: newPage.id,
          versionNumber: 1,
          contentMarkdown: template,
          sourceBlocks: [],
          origin: "manual-create",
          changeSummary: "Page created manually",
        },
      });

      return newPage;
    });

    return NextResponse.json(page, { status: 201 });
  } catch (error) {
    console.error("Failed to create page:", error);
    return NextResponse.json(
      { error: "Failed to create page" },
      { status: 500 }
    );
  }
}
