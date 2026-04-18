# Lore Wiki: System Design Specification

## Private Offline Wiki for Fictional World Lore

**Version:** 1.0  
**Date:** 2026-04-18  
**Author:** Devin (System Architect)

---

## Table of Contents

1. [High-Level System Architecture](#1-high-level-system-architecture)
2. [Detailed Component Breakdown](#2-detailed-component-breakdown)
   - 2a. Data Ingestion Pipeline
   - 2b. Wiki Entity Extraction & Page Generation
   - 2c. Edit/Versioning Data Model
   - 2d. Conflict Resolution on Re-Ingestion
   - 2e. RAG Pipeline
   - 2f. Vector Index Rebuild Workflow
   - 2g. Backup & Export Strategy
3. [Recommended Technology Stack](#3-recommended-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Folder / Project Structure](#5-folder--project-structure)
6. [Example Code Snippets](#6-example-code-snippets)
7. [Incremental Update Strategy](#7-incremental-update-strategy)
8. [Deployment & Security](#8-deployment--security)
9. [Persistence Verification Checklist](#9-persistence-verification-checklist)

---

## 1. High-Level System Architecture

### System Overview

The system is composed of four major subsystems:

1. **Ingestion Pipeline** (offline, batch process) — parses `.docx` files, extracts entities, and stores verbatim text in PostgreSQL.
2. **Wiki Application** (Next.js full-stack) — serves wiki pages, supports editing, version history, and conflict resolution.
3. **Q&A / RAG System** (on-demand) — retrieves from vector index + wiki pages to answer natural language questions.
4. **Vector Index Builder** (offline, on-demand) — rebuilds the pgvector embeddings from current DB state.

### Data Flow Diagram (Text)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INGESTION PIPELINE                          │
│                      (Python, offline batch)                       │
│                                                                    │
│  .docx files                                                       │
│      │                                                             │
│      ▼                                                             │
│  ┌──────────────┐    ┌───────────────────┐    ┌──────────────────┐ │
│  │ python-docx  │───▶│  Entity Extractor  │───▶│  DB Writer       │ │
│  │ Parser       │    │  (LLM classifier)  │    │  (PostgreSQL)    │ │
│  │              │    │                     │    │                  │ │
│  │ Extracts:    │    │ LLM identifies:     │    │ Writes:          │ │
│  │ - headings   │    │ - entity names      │    │ - pages table    │ │
│  │ - paragraphs │    │ - entity types      │    │ - versions table │ │
│  │ - tables     │    │ - section routing    │    │ - source_chunks  │ │
│  │ - styles     │    │                     │    │ - cross_links    │ │
│  │              │    │ LLM does NOT:       │    │                  │ │
│  │              │    │ - write wiki content │    │                  │ │
│  │              │    │ - paraphrase text   │    │                  │ │
│  │              │    │ - fill gaps          │    │                  │ │
│  └──────────────┘    └───────────────────┘    └──────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     PERSISTENT STORAGE LAYER                       │
│                                                                    │
│  ┌─────────────────────────────────────┐                           │
│  │        PostgreSQL (Neon)            │                           │
│  │                                     │                           │
│  │  ┌─────────┐  ┌──────────┐         │                           │
│  │  │  pages   │  │ versions │         │                           │
│  │  └─────────┘  └──────────┘         │                           │
│  │  ┌──────────────┐  ┌─────────────┐ │                           │
│  │  │source_chunks │  │ cross_links │ │                           │
│  │  └──────────────┘  └─────────────┘ │                           │
│  │  ┌───────────────────┐             │                           │
│  │  │ embeddings (pgvector)│           │                           │
│  │  └───────────────────┘             │                           │
│  │  ┌─────────────────┐              │                           │
│  │  │ index_build_log │              │                           │
│  │  └─────────────────┘              │                           │
│  └─────────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────────────┐
│    WIKI APPLICATION      │   │     Q&A / RAG SYSTEM             │
│    (Next.js on Vercel    │   │     (API route in Next.js)       │
│     or Docker)           │   │                                  │
│                          │   │  User question                   │
│  WRITE PATH (immediate): │   │      │                           │
│  Edit → API route        │   │      ▼                           │
│    → INSERT version row  │   │  Embed question                  │
│    → UPDATE page row     │   │      │                           │
│    → Response: 200 OK    │   │      ▼                           │
│                          │   │  pgvector similarity search      │
│  READ PATH:              │   │      │                           │
│  Request → API route     │   │      ▼                           │
│    → SELECT from pages   │   │  Retrieve top-K chunks           │
│    → Render wiki page    │   │  (from source_chunks + pages)    │
│                          │   │      │                           │
│                          │   │      ▼                           │
│                          │   │  LLM generates answer            │
│                          │   │  (with citations, free to        │
│                          │   │   synthesize & reason)           │
│                          │   │      │                           │
│                          │   │      ▼                           │
│                          │   │  Response with source tags       │
└──────────────────────────┘   └──────────────────────────────────┘
                                        │
                ┌───────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────┐
│              VECTOR INDEX BUILDER                                │
│              (Python script, on-demand)                          │
│                                                                  │
│  Triggered manually: `python rebuild_index.py`                   │
│                                                                  │
│  1. Reads all source_chunks + current wiki page content from DB  │
│  2. Generates embeddings via sentence-transformers               │
│  3. UPSERTS into pgvector embeddings table                       │
│  4. Logs build timestamp to index_build_log                      │
│                                                                  │
│  Safe to re-run. Never drops relational data.                    │
│  Only replaces/updates embedding vectors.                        │
└──────────────────────────────────────────────────────────────────┘
```

### Key Architectural Separation

| Path | Trigger | Latency | Storage Target |
|------|---------|---------|----------------|
| **Write Path** (wiki edits) | User clicks Save | Synchronous, immediate | PostgreSQL `pages` + `versions` tables |
| **Read Path** (wiki view) | User loads page | Synchronous | PostgreSQL `pages` table |
| **Ingestion Path** | Operator runs pipeline | Batch (minutes) | PostgreSQL `pages`, `versions`, `source_chunks` |
| **Q&A Index Path** | Operator runs rebuild | Batch (minutes) | PostgreSQL `embeddings` table (pgvector) |
| **Q&A Query Path** | User asks question | Synchronous | Reads from pgvector + `pages` |

The write path and Q&A index path are **intentionally decoupled**. Wiki edits are durable immediately. The Q&A system reflects edits only after an explicit rebuild. This is documented in the UI via a staleness indicator.

---

## 2. Detailed Component Breakdown

### 2a. Data Ingestion Pipeline

#### Overview

The ingestion pipeline is an offline Python process that:
1. Reads `.docx` files using `python-docx`
2. Extracts structured content (headings, paragraphs, tables) preserving original text verbatim
3. Uses an LLM **solely** as a classifier/router to identify entity mentions, entity types, and which wiki section a text block belongs to
4. Stores verbatim source text in the database, linked to entity pages

#### Source Fidelity Enforcement — How It Works

The pipeline enforces source fidelity through a **strict separation of concerns**:

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  TEXT EXTRACTOR  │────▶│   LLM CLASSIFIER     │────▶│   DB WRITER     │
│  (deterministic) │     │   (advisory only)     │     │  (verbatim)     │
│                  │     │                        │     │                 │
│  Outputs:        │     │  Inputs:               │     │  Inputs:        │
│  - raw text      │     │  - raw text chunks     │     │  - raw text     │
│  - doc name      │     │                        │     │  - entity_name  │
│  - heading path  │     │  Outputs (structured): │     │  - entity_type  │
│  - paragraph idx │     │  - entity_name: str    │     │  - section_type │
│                  │     │  - entity_type: enum   │     │  - doc_source   │
│                  │     │  - section_type: enum  │     │  - heading_path │
│                  │     │  - confidence: float   │     │                 │
│                  │     │                        │     │  The DB writer  │
│                  │     │  The LLM NEVER outputs │     │  stores the     │
│                  │     │  rewritten text.       │     │  ORIGINAL text  │
│                  │     │  It only outputs       │     │  from the       │
│                  │     │  classification labels.│     │  extractor,     │
│                  │     │                        │     │  NOT any LLM    │
│                  │     │                        │     │  output.        │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
```

**Critical implementation detail:** The LLM's output is a **structured JSON object** containing only classification labels (entity name, type, section assignment). The **text content** that gets stored in the database is always the original text from `python-docx`, never text generated or returned by the LLM. The LLM response schema is enforced via JSON mode / function calling to make it structurally impossible for the LLM to inject prose.

#### Detailed Steps

**Step 1: Document Parsing**

```python
# python-docx extracts:
# - document.paragraphs (with style info: Heading 1, Heading 2, Normal, etc.)
# - document.tables (with cell text)
# - Paragraph ordering is preserved exactly as in the .docx
```

The parser walks each document and produces an ordered list of `ContentBlock` objects:

```python
@dataclass
class ContentBlock:
    doc_filename: str          # e.g., "world_history_vol1.docx"
    heading_path: list[str]    # e.g., ["Chapter 3", "The Northern Wars", "Key Battles"]
    paragraph_index: int       # position within the document
    text: str                  # verbatim text content
    style: str                 # paragraph style name from .docx
    block_type: str            # "paragraph" | "table_cell" | "heading"
    content_hash: str          # SHA-256 of the text, for dedup and change detection
```

**Step 2: Entity Classification (LLM as classifier only)**

Each `ContentBlock` (or a sliding window of blocks for context) is sent to the LLM with a prompt like:

```
You are a classifier. Given the following text extracted from a fictional 
world document, identify:

1. The primary entity this text is about (exact name as it appears in text)
2. The entity type (one of: character, location, era, event, faction, artifact, 
   concept, species, other)
3. The wiki section this text belongs to (one of: overview, attributes, 
   relationships, history, appearances, abilities, culture, geography, 
   timeline, other)
4. Any other entities mentioned (for cross-linking)
5. Your confidence (0.0 to 1.0)

IMPORTANT: Return ONLY the structured classification. Do NOT rewrite, 
summarize, or paraphrase the text in any way.

Text:
"""
{content_block.text}
"""

Respond in JSON format only.
```

The LLM returns:
```json
{
  "primary_entity": "Kael Stormborn",
  "entity_type": "character",
  "section_type": "history",
  "mentioned_entities": ["Ironhold", "The Sundering"],
  "confidence": 0.92
}
```

**Step 3: Database Storage**

The DB writer takes:
- The **original `ContentBlock.text`** (from python-docx, never from LLM)
- The **classification labels** (from LLM)

And writes them to the database. If a page for `"Kael Stormborn"` doesn't exist, it creates one. If it does exist but was ingested (not manually edited), it appends. If it was manually edited, it flags a conflict (see §2d).

**Step 4: Cross-Link Generation**

After all blocks are processed, the system scans each page's content for mentions of other known entity names and creates entries in the `cross_links` table. This is a deterministic string-matching operation, not an LLM task.

#### Chunking Strategy for Ingestion

Documents are chunked at **heading boundaries** first (each heading starts a new logical section), then large sections are split at paragraph boundaries into chunks of ~500-1000 tokens. The heading path is preserved as metadata on every chunk, ensuring citations can point back to the exact location in the source document.

---

### 2b. Wiki Entity Extraction & Page Generation Strategy

#### Entity Identification

Entities are identified in two passes:

**Pass 1 — Heading-Based Extraction (deterministic):**
- Top-level and second-level headings in `.docx` files often correspond to entity names
- Pattern matching: headings like "Chapter N: [Entity Name]", "[Entity Name]", "The [Entity Name]"
- These are treated as high-confidence entity candidates

**Pass 2 — LLM Classification (advisory):**
- Each content block is classified by the LLM (as described in §2a)
- The LLM identifies the primary entity the text refers to
- Entities that appear across multiple documents or sections are aggregated

**Entity Deduplication:**
- Exact name matches are merged
- The LLM is asked (in a separate classification step) whether two similar names refer to the same entity (e.g., "Kael" and "Kael Stormborn")
- Dedup results are stored and can be manually overridden by the user

#### Page Generation — Source Fidelity Guarantee

Each wiki page is assembled as follows:

```
For entity E:
  1. Collect all ContentBlocks classified as relating to E
  2. Group blocks by section_type (overview, history, relationships, etc.)
  3. Within each section, order blocks by (doc_filename, paragraph_index)
  4. For each section:
     - If blocks exist: render the VERBATIM text of each block, 
       each with a citation marker [Source: filename.docx, §heading_path]
     - If no blocks exist: render "Not documented in source materials"
  5. Scan all text for mentions of other entity names → generate hyperlinks
```

**What the LLM does NOT do during page generation:**
- ❌ Write an "overview" or "summary" of the entity
- ❌ Combine or rephrase multiple source passages into a unified narrative
- ❌ Fill in "Relationships" based on inference from mentions
- ❌ Generate any text that doesn't exist character-for-character in a `.docx`

**What the LLM DOES do (classification only):**
- ✅ Determine which entity a text block belongs to
- ✅ Determine which section (overview, history, etc.) a text block maps to
- ✅ Identify cross-references to other entities
- ✅ Assess confidence scores

The page content stored in the database is a structured JSON document:

```json
{
  "entity_name": "Kael Stormborn",
  "entity_type": "character",
  "sections": {
    "overview": {
      "blocks": [
        {
          "text": "Kael Stormborn was the last commander of the Northern Guard...",
          "source_doc": "world_history_vol1.docx",
          "heading_path": ["Chapter 5", "Commanders of the North"],
          "paragraph_index": 142,
          "content_hash": "a3f2b8..."
        }
      ]
    },
    "relationships": {
      "blocks": []  // Empty → UI renders "Not documented in source materials"
    },
    "history": {
      "blocks": [
        {
          "text": "During the Siege of Ironhold, Kael led a desperate...",
          "source_doc": "world_history_vol1.docx",
          "heading_path": ["Chapter 7", "The Siege of Ironhold"],
          "paragraph_index": 298,
          "content_hash": "d7e1c4..."
        },
        {
          "text": "After the fall of Ironhold, Kael retreated to...",
          "source_doc": "northern_chronicles.docx",
          "heading_path": ["Part II", "The Retreat"],
          "paragraph_index": 55,
          "content_hash": "b9a3f1..."
        }
      ]
    }
  }
}
```

Each block's `text` field is a **direct copy** from `ContentBlock.text`, which itself is a verbatim extraction from `python-docx`. At no point does the LLM write or rewrite this text.

---

### 2c. Edit/Versioning Data Model

#### Core Schema (see §4 for full SQL)

Every wiki page has:
- A `pages` row with the **current** content and metadata
- A `versions` row for **every** historical state, including the initial AI-extracted version

#### Version Lifecycle

```
1. Ingestion creates page → version 1 (origin: "ai-extracted")
2. User edits page → version 2 (origin: "manual-edit")
3. User edits again → version 3 (origin: "manual-edit")
4. Re-ingestion finds new content → conflict flagged (NOT auto-merged)
5. User resolves conflict → version 4 (origin: "conflict-resolution")
```

#### Edit Workflow

1. User clicks "Edit" on a wiki page
2. Frontend loads current `pages.content_markdown` into the Markdown editor
3. User makes changes and clicks "Save"
4. API route:
   - Inserts a new `versions` row with the previous content (snapshot before edit)
   - Updates the `pages` row with the new content
   - Sets `pages.last_modified = NOW()`, increments `pages.version_number`
   - All in a single database transaction — atomic, immediate, durable
5. Response: 200 OK with updated page

#### Version History & Restore

- GET `/api/pages/:slug/versions` → returns all versions, ordered by `created_at DESC`
- GET `/api/pages/:slug/versions/:version_id` → returns a specific version's content
- POST `/api/pages/:slug/restore/:version_id` → creates a NEW version whose content is copied from the specified historical version (never deletes history)

#### Diff View

- The frontend uses a diffing library (e.g., `diff` npm package or `jsdiff`) to compute and render a side-by-side or unified diff between any two versions
- Diffs are computed on-the-fly from stored version content — not pre-computed

---

### 2d. Conflict Resolution on Re-Ingestion

#### The Problem

When new `.docx` files are ingested (or existing ones are updated), the pipeline may produce new or updated content for entities that already have wiki pages with manual edits. Silently overwriting edits would violate edit safety.

#### Resolution Strategy: Three-Way Merge with Human Review

```
                     ┌──────────────────────────┐
                     │   Re-ingestion detects    │
                     │   entity page exists      │
                     └────────────┬─────────────┘
                                  │
                     ┌────────────▼─────────────┐
                     │  Was page manually edited?│
                     │  (origin != "ai-extracted"│
                     │   on any version)         │
                     └────────────┬─────────────┘
                           │             │
                          YES            NO
                           │             │
              ┌────────────▼───┐   ┌─────▼──────────────┐
              │  Create         │   │  Safe to update:    │
              │  conflict_flag  │   │  Append new blocks, │
              │  on page        │   │  create new version │
              │                 │   │  (origin:           │
              │                 │   │   "ai-extracted")   │
              └────────┬───────┘   └─────────────────────┘
                       │
          ┌────────────▼──────────────────┐
          │  Store incoming content as     │
          │  pending_ingestion record      │
          │  (NOT applied to page)         │
          └────────────┬──────────────────┘
                       │
          ┌────────────▼──────────────────┐
          │  UI shows conflict banner:     │
          │  "New source material found    │
          │   for this entity. Review      │
          │   incoming changes."           │
          │                                │
          │  User sees:                    │
          │  - Current page (with edits)   │
          │  - Incoming source text        │
          │  - Diff between them           │
          │                                │
          │  User can:                     │
          │  - Accept incoming (replaces)  │
          │  - Keep current (ignores)      │
          │  - Merge manually (edits)      │
          └────────────────────────────────┘
```

#### Implementation Details

- The `pages` table has a `conflict_status` column: `null` (no conflict), `"pending"` (unresolved), `"resolved"`
- A `pending_ingestions` table stores the incoming content that triggered the conflict
- The UI surfaces a list of all pages with unresolved conflicts on a dedicated "Conflicts" dashboard
- Resolving a conflict creates a new version with `origin = "conflict-resolution"`

---

### 2e. RAG Pipeline

#### Architecture

```
User Question
     │
     ▼
┌─────────────────────┐
│ Embed question using │
│ sentence-transformers│
│ (all-MiniLM-L6-v2)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────┐
│ pgvector similarity search  │
│ (cosine distance)           │
│                             │
│ Search across:              │
│ - source_chunks embeddings  │
│ - wiki page embeddings      │
│                             │
│ Returns top-K (K=10)        │
│ with source metadata        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Re-rank results             │
│ (cross-encoder or           │
│  reciprocal rank fusion)    │
│                             │
│ Select top-5 for context    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│ LLM Answer Generation                       │
│                                             │
│ System prompt:                              │
│ "Answer the question using ONLY the         │
│  provided context. Cite each claim with     │
│  [Source: doc_name, §section] or            │
│  [Wiki: page_name]. Distinguish between     │
│  source document content and wiki edits.    │
│  If a wiki page has been manually edited,   │
│  note this."                                │
│                                             │
│ Context includes for each chunk:            │
│ - The chunk text                            │
│ - Source type: "source_document" or          │
│   "wiki_page"                               │
│ - If wiki_page: whether it has manual edits │
│ - Source citation metadata                  │
└─────────────────────────────────────────────┘
```

#### Chunking Strategy for RAG

- **Source documents:** chunked at paragraph/heading boundaries, ~500 tokens per chunk, with 50-token overlap between chunks. Heading path preserved as metadata.
- **Wiki pages:** each section of a wiki page is a separate chunk. The entity name + section name is prepended as metadata.
- **Chunk metadata stored:** `chunk_id`, `source_type` (document vs wiki_page), `source_identifier` (filename or page slug), `heading_path`, `content_hash`, `text`

#### Embedding Model

**Recommended: `all-MiniLM-L6-v2`** (via `sentence-transformers`)

- **Why:** Free, open-source, 384-dimensional vectors (low storage), fast inference, good quality for semantic search. Runs locally — no API costs.
- **Alternative for higher quality:** `BAAI/bge-small-en-v1.5` (also free, slightly better retrieval quality, same dimensionality).
- Both models can run on CPU, important for a free-tier deployment.

#### Answer Citation Format

The RAG answer marks each claim with its source:

```
Kael Stormborn was the last commander of the Northern Guard 
[Source: world_history_vol1.docx, §Chapter 5 > Commanders of the North].

After the Siege of Ironhold, he retreated to the Greymist Peaks 
[Source: northern_chronicles.docx, §Part II > The Retreat].

Note: The wiki page for "Kael Stormborn" has been manually edited 
since the last index build. Edited wiki content may not be reflected 
in this answer.
```

---

### 2f. Vector Index Rebuild Workflow

#### Operator Workflow

```bash
# To update the Q&A system after edits or new document ingestion:
python scripts/rebuild_index.py

# This rebuilds the vector index without affecting any wiki content or edit history.
```

#### What the Rebuild Script Does

1. **Reads** all `source_chunks` from PostgreSQL
2. **Reads** all current wiki page content from `pages` table
3. **Generates embeddings** for each chunk using `sentence-transformers`
4. **Upserts** embeddings into the `embeddings` table (pgvector):
   - Existing embeddings with the same `chunk_id` are updated
   - New chunks get new embeddings
   - Chunks that no longer exist are deleted (orphan cleanup)
5. **Logs** the build timestamp, chunk count, and duration to `index_build_log`
6. **Reports** summary: "Indexed N chunks from M documents and P wiki pages in T seconds"

#### Safety Guarantees

- **Idempotent:** Safe to run multiple times. Uses UPSERT, not INSERT.
- **Non-destructive:** Never touches `pages`, `versions`, or `source_chunks` tables — only reads from them.
- **Atomic:** The rebuild runs in a transaction. If it fails partway, the old embeddings remain intact.
- **Resumable:** If interrupted, re-run from scratch — it will complete cleanly.

#### Staleness Indicator

The UI queries `index_build_log` for the most recent build timestamp and compares it against the most recent `pages.last_modified` or `source_chunks.created_at`. If any content is newer than the last build, the UI displays:

```
⚠ Q&A index last built: 3 days ago. 12 pages have been edited since then.
Changes will not appear in Q&A answers until re-indexed.
[Rebuild Index] (admin button, triggers the rebuild script)
```

---

### 2g. Backup & Export Strategy

#### Export Formats

1. **Full JSON Export**
   - Exports all pages with all versions, source chunks, cross-links, and metadata
   - Command: `python scripts/export.py --format json --output backup.json`
   - Produces a single JSON file or a directory of per-page JSON files

2. **Markdown Export**
   - Exports each wiki page as a standalone `.md` file in a directory structure mirroring entity types
   - Command: `python scripts/export.py --format markdown --output ./wiki-export/`
   - Structure:
     ```
     wiki-export/
       characters/
         kael-stormborn.md
         lyra-dawnwhisper.md
       locations/
         ironhold.md
         greymist-peaks.md
       ...
     ```

3. **Database Dump**
   - Standard `pg_dump` for full PostgreSQL backup
   - Command: `pg_dump $DATABASE_URL > backup.sql`

#### Automated Backup

- A cron job or scheduled task runs the JSON export weekly
- Database dumps can be configured via the hosting provider (Neon provides daily backups on all plans)

#### Restore

- JSON import: `python scripts/import.py --input backup.json` (upserts, never drops)
- SQL restore: `psql $DATABASE_URL < backup.sql`
- Markdown import: not supported for restore (lossy format), used for human reading only

---

## 3. Recommended Technology Stack

| Layer | Technology | Justification |
|-------|-----------|---------------|
| **Frontend** | Next.js 14 (App Router) + React 18 | Required by constraints. App Router provides server components for fast page loads, API routes for backend logic. |
| **Styling** | Tailwind CSS | Minimal, utility-first. Easy to create clean wiki-like UI. No runtime CSS overhead. |
| **Markdown Editor** | `@uiw/react-md-editor` or `react-markdown` + `textarea` | Markdown is simpler than rich-text for versioning and diffing. Stores cleanly in DB. Renders predictably. |
| **Diff View** | `react-diff-viewer-continued` | Mature library for side-by-side and unified diffs of text content. |
| **Backend** | Next.js API Routes (Route Handlers) | Co-located with frontend. No separate server to deploy. Sufficient for a single-user wiki. |
| **Database** | **Neon** (serverless PostgreSQL) | **Why Neon:** Free tier (0.5 GB storage, 190 compute hours/month — more than enough for a personal wiki). Serverless — no container to manage. Fully managed PostgreSQL with branching. Survives all redeployments. Accessible from Vercel serverless functions. **Why not Supabase:** Supabase is also viable but adds unnecessary abstraction (auth, realtime) we don't need. **Why not Railway:** Railway's free tier is more limited and requires a persistent container. |
| **Vector Store** | **pgvector** (PostgreSQL extension on Neon) | **Why pgvector:** Reuses the same PostgreSQL database — no additional service to deploy, manage, or pay for. Neon supports pgvector natively. Embeddings are stored in the same durable, persistent database as all other data. No risk of ephemeral storage. **Why not Chroma/Qdrant:** Would require a separate persistent service, adding deployment complexity and cost. For a corpus of ~10 documents (~3000 pages), pgvector performance is more than adequate. |
| **Embeddings** | `sentence-transformers` (`all-MiniLM-L6-v2`) | Free, open-source, runs locally on CPU. 384-dim vectors keep storage small. Good retrieval quality for this corpus size. |
| **LLM (Classification)** | **Ollama** (local, `mistral` or `llama3`) or **OpenAI API** (gpt-4o-mini) | For classification tasks only. Ollama is free and offline. OpenAI gpt-4o-mini is cheap ($0.15/1M input tokens) and more accurate for structured extraction. User can choose based on privacy preference. |
| **LLM (RAG Answers)** | Same as above | Q&A answer generation is exempt from source fidelity — can use any LLM. |
| **Document Parsing** | `python-docx` | Required by constraints. Preserves headings, styles, tables. Mature library. |
| **Ingestion Runtime** | Python 3.11+ | `python-docx`, `sentence-transformers`, and `psycopg2` are all Python. The ingestion pipeline runs as a standalone Python script, not inside Next.js. |
| **Auth** | NextAuth.js with credentials provider (or Vercel's built-in password protection) | Simple password-based auth for a single-user wiki. No OAuth complexity needed. |
| **Hosting** | **Vercel** (frontend + API) + **Neon** (database) | Vercel for the Next.js app (free tier). Neon for all persistent state. All stateful data lives on Neon — nothing on Vercel's filesystem. |
| **Local Alternative** | Docker Compose | If the user prefers fully offline: a single `docker-compose.yml` with Next.js app + PostgreSQL (with pgvector) + Ollama. All data in Docker volumes. |

### Persistence Justification

Every storage decision passes the litmus test: **"Does it survive a full redeploy?"**

| Data | Storage | Survives redeploy? |
|------|---------|-------------------|
| Wiki pages | Neon PostgreSQL | ✅ Yes — external managed database |
| Version history | Neon PostgreSQL | ✅ Yes |
| Source chunks | Neon PostgreSQL | ✅ Yes |
| Embeddings | Neon PostgreSQL (pgvector) | ✅ Yes — same database |
| Index build log | Neon PostgreSQL | ✅ Yes |
| User auth sessions | NextAuth.js session tokens (JWT, stateless) | ✅ Yes — no server state needed |
| Uploaded .docx files | Not stored on Vercel — processed by pipeline, original files kept by user | ✅ N/A — user retains originals |

---

## 4. Database Schema

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- PAGES TABLE
-- Stores the current state of each wiki page
-- ============================================================
CREATE TABLE pages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT UNIQUE NOT NULL,             -- URL-safe identifier, e.g., "kael-stormborn"
    entity_name     TEXT NOT NULL,                    -- Display name, e.g., "Kael Stormborn"
    entity_type     TEXT NOT NULL DEFAULT 'other',    -- character, location, era, event, faction, artifact, concept, species, other
    
    -- Content: stored as Markdown for editability and diffing
    content_markdown TEXT NOT NULL DEFAULT '',
    
    -- Structured content: the source-extracted blocks (JSON)
    -- This preserves the per-block citations even after user edits to content_markdown
    source_blocks   JSONB DEFAULT '[]'::jsonb,
    
    -- Metadata
    version_number  INTEGER NOT NULL DEFAULT 1,
    origin          TEXT NOT NULL DEFAULT 'ai-extracted',  -- 'ai-extracted', 'manual-edit', 'conflict-resolution'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_modified   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Conflict tracking
    conflict_status TEXT DEFAULT NULL,                -- NULL (no conflict), 'pending', 'resolved'
    
    -- Search optimization
    search_vector   TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', entity_name || ' ' || content_markdown)
    ) STORED
);

CREATE INDEX idx_pages_slug ON pages (slug);
CREATE INDEX idx_pages_entity_type ON pages (entity_type);
CREATE INDEX idx_pages_conflict ON pages (conflict_status) WHERE conflict_status IS NOT NULL;
CREATE INDEX idx_pages_search ON pages USING GIN (search_vector);

-- ============================================================
-- VERSIONS TABLE
-- Stores every historical version of every page
-- ============================================================
CREATE TABLE versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id         UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    version_number  INTEGER NOT NULL,
    
    -- Snapshot of page content at this version
    content_markdown TEXT NOT NULL,
    source_blocks   JSONB DEFAULT '[]'::jsonb,
    
    -- Metadata
    origin          TEXT NOT NULL,                    -- 'ai-extracted', 'manual-edit', 'conflict-resolution', 'restore'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Change summary (optional, for display in version history)
    change_summary  TEXT DEFAULT NULL,
    
    UNIQUE(page_id, version_number)
);

CREATE INDEX idx_versions_page_id ON versions (page_id);
CREATE INDEX idx_versions_created_at ON versions (created_at DESC);

-- ============================================================
-- SOURCE_CHUNKS TABLE
-- Stores raw text chunks from .docx files with metadata
-- ============================================================
CREATE TABLE source_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Source document info
    doc_filename    TEXT NOT NULL,                    -- e.g., "world_history_vol1.docx"
    heading_path    TEXT[] NOT NULL DEFAULT '{}',     -- e.g., {"Chapter 5", "Commanders of the North"}
    paragraph_index INTEGER NOT NULL,
    block_type      TEXT NOT NULL DEFAULT 'paragraph', -- 'paragraph', 'table_cell', 'heading'
    
    -- Content
    text            TEXT NOT NULL,                    -- Verbatim text from .docx
    content_hash    TEXT NOT NULL,                    -- SHA-256 for dedup and change detection
    
    -- Classification (from LLM)
    entity_name     TEXT,                             -- Primary entity this chunk is about
    entity_type     TEXT,                             -- Classified entity type
    section_type    TEXT,                             -- Classified section type
    confidence      REAL DEFAULT 0.0,                 -- LLM classification confidence
    
    -- Linking
    page_id         UUID REFERENCES pages(id) ON DELETE SET NULL,  -- Which wiki page this chunk belongs to
    
    -- Metadata
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ingestion_run_id TEXT,                            -- Groups chunks from the same ingestion run
    
    UNIQUE(doc_filename, paragraph_index, content_hash)
);

CREATE INDEX idx_source_chunks_page_id ON source_chunks (page_id);
CREATE INDEX idx_source_chunks_doc ON source_chunks (doc_filename);
CREATE INDEX idx_source_chunks_entity ON source_chunks (entity_name);
CREATE INDEX idx_source_chunks_hash ON source_chunks (content_hash);

-- ============================================================
-- CROSS_LINKS TABLE
-- Tracks relationships between wiki pages
-- ============================================================
CREATE TABLE cross_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_page_id  UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    target_page_id  UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    mention_context TEXT,                             -- The sentence containing the mention
    
    UNIQUE(source_page_id, target_page_id)
);

CREATE INDEX idx_cross_links_source ON cross_links (source_page_id);
CREATE INDEX idx_cross_links_target ON cross_links (target_page_id);

-- ============================================================
-- EMBEDDINGS TABLE (pgvector)
-- Stores vector embeddings for RAG retrieval
-- ============================================================
CREATE TABLE embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- What this embedding represents
    source_type     TEXT NOT NULL,                    -- 'source_chunk' or 'wiki_page_section'
    source_id       UUID NOT NULL,                    -- References source_chunks.id or pages.id
    chunk_text      TEXT NOT NULL,                    -- The text that was embedded
    content_hash    TEXT NOT NULL,                    -- For change detection during rebuild
    
    -- The embedding vector (384 dimensions for all-MiniLM-L6-v2)
    embedding       vector(384) NOT NULL,
    
    -- Metadata for retrieval context
    metadata        JSONB DEFAULT '{}'::jsonb,        -- doc_filename, heading_path, entity_name, etc.
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(source_type, source_id, content_hash)
);

-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX idx_embeddings_vector ON embeddings 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================
-- INDEX_BUILD_LOG TABLE
-- Tracks when the vector index was last rebuilt
-- ============================================================
CREATE TABLE index_build_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',   -- 'running', 'completed', 'failed'
    
    -- Stats
    chunks_indexed  INTEGER DEFAULT 0,
    pages_indexed   INTEGER DEFAULT 0,
    duration_seconds REAL,
    
    -- Error info (if failed)
    error_message   TEXT,
    
    -- Build configuration
    embedding_model TEXT NOT NULL,                     -- e.g., 'all-MiniLM-L6-v2'
    build_trigger   TEXT DEFAULT 'manual'              -- 'manual', 'post-ingestion', 'scheduled'
);

CREATE INDEX idx_build_log_completed ON index_build_log (completed_at DESC);

-- ============================================================
-- PENDING_INGESTIONS TABLE
-- Stores incoming content when a conflict is detected
-- ============================================================
CREATE TABLE pending_ingestions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id         UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    
    -- The incoming content that would update/replace the page
    incoming_content_markdown TEXT NOT NULL,
    incoming_source_blocks JSONB DEFAULT '[]'::jsonb,
    
    -- Source info
    doc_filename    TEXT NOT NULL,
    ingestion_run_id TEXT,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    resolution      TEXT                              -- 'accepted', 'rejected', 'merged'
);

CREATE INDEX idx_pending_page ON pending_ingestions (page_id) WHERE NOT resolved;

-- ============================================================
-- DOCUMENTS TABLE
-- Tracks ingested .docx files
-- ============================================================
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        TEXT UNIQUE NOT NULL,
    file_hash       TEXT NOT NULL,                    -- SHA-256 of the file, for change detection
    page_count      INTEGER,                          -- Approximate page count
    chunk_count     INTEGER DEFAULT 0,                -- Number of chunks extracted
    
    first_ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    ingestion_status TEXT NOT NULL DEFAULT 'pending'  -- 'pending', 'processing', 'completed', 'failed'
);
```

---

## 5. Folder / Project Structure

```
lore-wiki/
├── docker-compose.yml              # Local deployment: app + PostgreSQL + Ollama
├── Dockerfile                      # Multi-stage: Python ingestion + Next.js app
├── package.json                    # Next.js dependencies
├── next.config.js                  # Next.js configuration
├── tailwind.config.ts              # Tailwind CSS config
├── tsconfig.json                   # TypeScript config
├── .env.example                    # Environment variable template
├── .env.local                      # Local env vars (gitignored)
│
├── prisma/                         # Database ORM
│   ├── schema.prisma               # Prisma schema matching §4
│   └── migrations/                 # Database migration files
│
├── src/
│   ├── app/                        # Next.js App Router
│   │   ├── layout.tsx              # Root layout with nav
│   │   ├── page.tsx                # Home / dashboard
│   │   ├── globals.css             # Global styles
│   │   │
│   │   ├── wiki/
│   │   │   ├── page.tsx            # Wiki index (list all entities, filter by type)
│   │   │   └── [slug]/
│   │   │       ├── page.tsx        # Wiki page view
│   │   │       ├── edit/
│   │   │       │   └── page.tsx    # Wiki page editor
│   │   │       └── history/
│   │   │           └── page.tsx    # Version history + diff view
│   │   │
│   │   ├── ask/
│   │   │   └── page.tsx            # Q&A interface
│   │   │
│   │   ├── conflicts/
│   │   │   └── page.tsx            # Conflict resolution dashboard
│   │   │
│   │   ├── admin/
│   │   │   └── page.tsx            # Admin: ingestion status, index rebuild, export
│   │   │
│   │   └── api/
│   │       ├── pages/
│   │       │   ├── route.ts                    # GET (list pages), POST (create page)
│   │       │   └── [slug]/
│   │       │       ├── route.ts                # GET (page), PUT (edit page)
│   │       │       ├── versions/
│   │       │       │   └── route.ts            # GET (version history)
│   │       │       └── restore/
│   │       │           └── route.ts            # POST (restore version)
│   │       │
│   │       ├── ask/
│   │       │   └── route.ts                    # POST (Q&A query)
│   │       │
│   │       ├── conflicts/
│   │       │   └── [id]/
│   │       │       └── route.ts                # POST (resolve conflict)
│   │       │
│   │       ├── index-status/
│   │       │   └── route.ts                    # GET (index staleness info)
│   │       │
│   │       ├── export/
│   │       │   └── route.ts                    # GET (export all pages as JSON/Markdown)
│   │       │
│   │       └── auth/
│   │           └── [...nextauth]/
│   │               └── route.ts                # NextAuth.js handler
│   │
│   ├── components/
│   │   ├── WikiPage.tsx            # Wiki page renderer (Markdown → HTML with cross-links)
│   │   ├── WikiEditor.tsx          # Markdown editor component
│   │   ├── VersionHistory.tsx      # Version list component
│   │   ├── DiffViewer.tsx          # Side-by-side diff component
│   │   ├── ConflictResolver.tsx    # Conflict merge UI
│   │   ├── QAInterface.tsx         # Q&A chat/search UI
│   │   ├── IndexStatus.tsx         # Staleness indicator component
│   │   ├── EntityCard.tsx          # Entity card for wiki index
│   │   ├── SearchBar.tsx           # Full-text search
│   │   ├── Sidebar.tsx             # Navigation sidebar
│   │   └── Layout.tsx              # Page layout wrapper
│   │
│   ├── lib/
│   │   ├── db.ts                   # Database client (Prisma)
│   │   ├── auth.ts                 # NextAuth configuration
│   │   ├── markdown.ts             # Markdown rendering utilities
│   │   └── cross-links.ts          # Cross-link detection and rendering
│   │
│   └── types/
│       └── index.ts                # TypeScript type definitions
│
├── scripts/                        # Python ingestion pipeline
│   ├── requirements.txt            # Python dependencies
│   ├── ingest.py                   # Main ingestion script
│   ├── parse_docx.py               # .docx parser (python-docx)
│   ├── classify_entities.py        # LLM entity classifier
│   ├── generate_pages.py           # Wiki page generator (verbatim assembly)
│   ├── rebuild_index.py            # Vector index rebuild script
│   ├── export.py                   # Backup/export script
│   ├── import.py                   # Restore/import script
│   └── config.py                   # Pipeline configuration
│
├── data/                           # Local data directory (gitignored)
│   └── docx/                       # Place .docx files here for ingestion
│
├── docs/
│   ├── SETUP.md                    # Setup and deployment guide
│   ├── OPERATOR_GUIDE.md           # How to ingest, rebuild, export
│   └── ARCHITECTURE.md             # This document (or a summary)
│
└── tests/
    ├── test_parser.py              # Tests for .docx parsing
    ├── test_classifier.py          # Tests for entity classification
    ├── test_ingestion.py           # Integration tests for pipeline
    └── test_api.ts                 # API route tests
```

---

## 6. Example Code Snippets

### 6a. `.docx` Ingestion and Entity Extraction

```python
# scripts/parse_docx.py
"""
Parses .docx files into ContentBlocks, preserving verbatim text.
"""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from docx import Document
from docx.opc.exceptions import PackageNotFoundError


@dataclass
class ContentBlock:
    doc_filename: str
    heading_path: list[str]
    paragraph_index: int
    text: str
    style: str
    block_type: str  # "paragraph" | "table_cell" | "heading"
    content_hash: str = field(init=False)

    def __post_init__(self):
        self.content_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def parse_docx(file_path: Path) -> list[ContentBlock]:
    """
    Parse a .docx file into an ordered list of ContentBlocks.
    All text is extracted verbatim — no transformation, no summarization.
    """
    try:
        doc = Document(str(file_path))
    except PackageNotFoundError:
        raise ValueError(f"Cannot open {file_path} — not a valid .docx file")

    blocks: list[ContentBlock] = []
    current_heading_path: list[str] = []
    heading_levels: list[int] = []

    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name if para.style else "Normal"

        # Track heading hierarchy
        if style_name.startswith("Heading"):
            try:
                level = int(style_name.split()[-1])
            except (ValueError, IndexError):
                level = 1

            # Pop headings at same or deeper level
            while heading_levels and heading_levels[-1] >= level:
                heading_levels.pop()
                current_heading_path.pop()

            current_heading_path.append(text)
            heading_levels.append(level)

            blocks.append(ContentBlock(
                doc_filename=file_path.name,
                heading_path=list(current_heading_path),
                paragraph_index=i,
                text=text,
                style=style_name,
                block_type="heading",
            ))
        else:
            blocks.append(ContentBlock(
                doc_filename=file_path.name,
                heading_path=list(current_heading_path),
                paragraph_index=i,
                text=text,
                style=style_name,
                block_type="paragraph",
            ))

    # Also extract table content
    for table_idx, table in enumerate(doc.tables):
        for row_idx, row in enumerate(table.rows):
            for cell_idx, cell in enumerate(row.cells):
                cell_text = cell.text.strip()
                if cell_text:
                    blocks.append(ContentBlock(
                        doc_filename=file_path.name,
                        heading_path=list(current_heading_path),
                        paragraph_index=len(doc.paragraphs) + table_idx * 1000 + row_idx * 100 + cell_idx,
                        text=cell_text,
                        style="TableCell",
                        block_type="table_cell",
                    ))

    return blocks


# scripts/classify_entities.py
"""
Uses LLM as a classifier ONLY. Never generates wiki content.
Returns structured classification labels for each ContentBlock.
"""
import json
from dataclasses import dataclass
from typing import Optional
import openai  # or use ollama


@dataclass
class EntityClassification:
    primary_entity: str
    entity_type: str  # character, location, era, event, faction, artifact, concept, species, other
    section_type: str  # overview, attributes, relationships, history, appearances, abilities, culture, geography, timeline, other
    mentioned_entities: list[str]
    confidence: float


CLASSIFICATION_PROMPT = """You are a strict classifier for fictional world content. 
Given a text block, return ONLY a JSON classification. Do NOT rewrite, summarize, 
or paraphrase the text. You must NEVER include the original text or any rewritten 
version of it in your response.

Classify the text block:
1. primary_entity: The exact name of the main entity this text is about (as it appears in the text)
2. entity_type: One of [character, location, era, event, faction, artifact, concept, species, other]
3. section_type: One of [overview, attributes, relationships, history, appearances, abilities, culture, geography, timeline, other]
4. mentioned_entities: List of other named entities mentioned in the text
5. confidence: Your confidence from 0.0 to 1.0

Text block:
\"\"\"
{text}
\"\"\"

Context — this text appears under these headings: {heading_path}

Respond with ONLY valid JSON. No other text."""


def classify_block(
    block: "ContentBlock",
    client: openai.OpenAI,
    model: str = "gpt-4o-mini",
) -> Optional[EntityClassification]:
    """
    Classify a content block using the LLM.
    The LLM returns ONLY classification labels — never content.
    """
    prompt = CLASSIFICATION_PROMPT.format(
        text=block.text,
        heading_path=" > ".join(block.heading_path) if block.heading_path else "(no heading context)",
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,  # Deterministic classification
            max_tokens=300,   # Classification doesn't need many tokens
        )

        result = json.loads(response.choices[0].message.content)

        return EntityClassification(
            primary_entity=result.get("primary_entity", "Unknown"),
            entity_type=result.get("entity_type", "other"),
            section_type=result.get("section_type", "other"),
            mentioned_entities=result.get("mentioned_entities", []),
            confidence=result.get("confidence", 0.0),
        )
    except (json.JSONDecodeError, KeyError, openai.APIError) as e:
        print(f"Classification failed for block at paragraph {block.paragraph_index}: {e}")
        return None


# scripts/ingest.py
"""
Main ingestion orchestrator.
Coordinates parsing, classification, and database storage.
"""
import uuid
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values
import hashlib
import openai

from parse_docx import parse_docx, ContentBlock
from classify_entities import classify_block, EntityClassification


def ingest_document(
    file_path: Path,
    db_conn,
    llm_client: openai.OpenAI,
    model: str = "gpt-4o-mini",
):
    """
    Ingest a single .docx file:
    1. Parse into ContentBlocks (verbatim text)
    2. Classify each block (LLM as classifier only)
    3. Store verbatim text + classification in DB
    4. Create/update wiki pages with verbatim content
    """
    ingestion_run_id = str(uuid.uuid4())
    file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

    print(f"Ingesting {file_path.name} (hash: {file_hash[:12]}...)")

    # Step 1: Parse .docx → ContentBlocks
    blocks = parse_docx(file_path)
    print(f"  Extracted {len(blocks)} content blocks")

    # Step 2: Classify each block
    classified_blocks: list[tuple[ContentBlock, EntityClassification]] = []
    for block in blocks:
        if block.block_type == "heading" and len(block.text.split()) <= 5:
            # Short headings are structural, not content — skip classification
            continue

        classification = classify_block(block, llm_client, model)
        if classification and classification.confidence >= 0.5:
            classified_blocks.append((block, classification))

    print(f"  Classified {len(classified_blocks)} blocks to entities")

    # Step 3: Group by entity
    entity_blocks: dict[str, list[tuple[ContentBlock, EntityClassification]]] = {}
    for block, classification in classified_blocks:
        entity_name = classification.primary_entity
        if entity_name not in entity_blocks:
            entity_blocks[entity_name] = []
        entity_blocks[entity_name].append((block, classification))

    # Step 4: Store in database
    cursor = db_conn.cursor()

    # Record the document
    cursor.execute("""
        INSERT INTO documents (filename, file_hash, chunk_count, ingestion_status)
        VALUES (%s, %s, %s, 'completed')
        ON CONFLICT (filename) DO UPDATE
        SET file_hash = EXCLUDED.file_hash,
            chunk_count = EXCLUDED.chunk_count,
            last_ingested_at = NOW(),
            ingestion_status = 'completed'
    """, (file_path.name, file_hash, len(classified_blocks)))

    for entity_name, items in entity_blocks.items():
        entity_type = items[0][1].entity_type
        slug = entity_name.lower().replace(" ", "-").replace("'", "")

        # Check if page exists
        cursor.execute("SELECT id, origin, version_number FROM pages WHERE slug = %s", (slug,))
        existing_page = cursor.fetchone()

        if existing_page:
            page_id, current_origin, current_version = existing_page

            # Check if page has been manually edited
            cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM versions 
                    WHERE page_id = %s AND origin = 'manual-edit'
                )
            """, (page_id,))
            has_manual_edits = cursor.fetchone()[0]

            if has_manual_edits:
                # CONFLICT: Page has manual edits — do NOT overwrite
                # Store as pending ingestion for user review
                incoming_markdown = _assemble_markdown(items)
                incoming_blocks_json = _assemble_source_blocks_json(items)

                cursor.execute("""
                    INSERT INTO pending_ingestions 
                    (page_id, incoming_content_markdown, incoming_source_blocks, 
                     doc_filename, ingestion_run_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (page_id, incoming_markdown, incoming_blocks_json,
                      file_path.name, ingestion_run_id))

                # Flag the page as having a conflict
                cursor.execute("""
                    UPDATE pages SET conflict_status = 'pending' WHERE id = %s
                """, (page_id,))

                print(f"  ⚠ Conflict detected for '{entity_name}' — stored as pending")
                continue
            else:
                # No manual edits — safe to append new content
                _append_to_page(cursor, page_id, current_version, items, ingestion_run_id)
                print(f"  Updated page for '{entity_name}'")
        else:
            # Create new page
            page_id = _create_page(cursor, slug, entity_name, entity_type, items, ingestion_run_id)
            print(f"  Created page for '{entity_name}'")

        # Store source chunks
        for block, classification in items:
            cursor.execute("""
                INSERT INTO source_chunks 
                (doc_filename, heading_path, paragraph_index, block_type, text, 
                 content_hash, entity_name, entity_type, section_type, confidence,
                 page_id, ingestion_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_filename, paragraph_index, content_hash) DO NOTHING
            """, (
                block.doc_filename, block.heading_path, block.paragraph_index,
                block.block_type, block.text, block.content_hash,
                classification.primary_entity, classification.entity_type,
                classification.section_type, classification.confidence,
                page_id, ingestion_run_id,
            ))

    db_conn.commit()
    print(f"  ✓ Ingestion complete for {file_path.name}")


def _assemble_markdown(items: list[tuple[ContentBlock, EntityClassification]]) -> str:
    """
    Assemble wiki page markdown from classified blocks.
    ALL TEXT IS VERBATIM from the .docx — no LLM-generated prose.
    """
    sections: dict[str, list[tuple[ContentBlock, EntityClassification]]] = {}
    for block, classification in items:
        section = classification.section_type
        if section not in sections:
            sections[section] = []
        sections[section].append((block, classification))

    section_order = [
        "overview", "attributes", "relationships", "history",
        "appearances", "abilities", "culture", "geography",
        "timeline", "other"
    ]

    all_sections = [
        "overview", "attributes", "relationships", "history",
        "appearances", "abilities", "culture", "geography",
        "timeline", "other"
    ]

    lines: list[str] = []

    for section_name in all_sections:
        display_name = section_name.replace("_", " ").title()
        lines.append(f"## {display_name}")
        lines.append("")

        if section_name in sections:
            for block, classification in sections[section_name]:
                # The text is VERBATIM from the .docx file
                lines.append(block.text)
                lines.append("")
                # Citation
                heading_str = " > ".join(block.heading_path) if block.heading_path else "N/A"
                lines.append(
                    f"*[Source: {block.doc_filename}, §{heading_str}]*"
                )
                lines.append("")
        else:
            lines.append("*Not documented in source materials*")
            lines.append("")

    return "\n".join(lines)


def _assemble_source_blocks_json(items):
    """Build the source_blocks JSONB array."""
    import json
    blocks = []
    for block, classification in items:
        blocks.append({
            "text": block.text,  # VERBATIM
            "source_doc": block.doc_filename,
            "heading_path": block.heading_path,
            "paragraph_index": block.paragraph_index,
            "content_hash": block.content_hash,
            "section_type": classification.section_type,
        })
    return json.dumps(blocks)


def _create_page(cursor, slug, entity_name, entity_type, items, ingestion_run_id):
    """Create a new wiki page from ingested content."""
    import json

    content_md = _assemble_markdown(items)
    source_blocks = _assemble_source_blocks_json(items)
    page_id = str(uuid.uuid4())

    cursor.execute("""
        INSERT INTO pages (id, slug, entity_name, entity_type, content_markdown, 
                          source_blocks, version_number, origin)
        VALUES (%s, %s, %s, %s, %s, %s, 1, 'ai-extracted')
    """, (page_id, slug, entity_name, entity_type, content_md, source_blocks))

    # Create initial version record
    cursor.execute("""
        INSERT INTO versions (page_id, version_number, content_markdown, 
                            source_blocks, origin, change_summary)
        VALUES (%s, 1, %s, %s, 'ai-extracted', 'Initial extraction from source documents')
    """, (page_id, content_md, source_blocks))

    return page_id


def _append_to_page(cursor, page_id, current_version, items, ingestion_run_id):
    """Append new source content to an existing page (no manual edits)."""
    import json

    # Get current content
    cursor.execute("SELECT content_markdown, source_blocks FROM pages WHERE id = %s", (page_id,))
    current_md, current_blocks = cursor.fetchone()

    # Assemble new content
    new_md = _assemble_markdown(items)
    new_blocks = _assemble_source_blocks_json(items)

    # Merge: append new content after existing
    merged_md = current_md + "\n\n---\n*New content from re-ingestion:*\n\n" + new_md

    existing_blocks = json.loads(current_blocks) if current_blocks else []
    incoming_blocks = json.loads(new_blocks) if new_blocks else []
    merged_blocks = json.dumps(existing_blocks + incoming_blocks)

    new_version = current_version + 1

    # Save version snapshot of previous state
    cursor.execute("""
        INSERT INTO versions (page_id, version_number, content_markdown, 
                            source_blocks, origin, change_summary)
        VALUES (%s, %s, %s, %s, 'ai-extracted', 'Re-ingestion: new source content added')
    """, (page_id, new_version, merged_md, merged_blocks))

    # Update page
    cursor.execute("""
        UPDATE pages 
        SET content_markdown = %s, source_blocks = %s, 
            version_number = %s, last_modified = NOW()
        WHERE id = %s
    """, (merged_md, merged_blocks, new_version, page_id))
```

### 6b. Saving a Page + Creating a Version Record

```typescript
// src/app/api/pages/[slug]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

// GET /api/pages/:slug — Retrieve a wiki page
export async function GET(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const page = await prisma.page.findUnique({
    where: { slug: params.slug },
    include: {
      crossLinksFrom: {
        include: { targetPage: { select: { slug: true, entityName: true } } },
      },
      sourceChunks: {
        select: { docFilename: true, headingPath: true, text: true },
        orderBy: { paragraphIndex: "asc" },
      },
    },
  });

  if (!page) {
    return NextResponse.json({ error: "Page not found" }, { status: 404 });
  }

  return NextResponse.json(page);
}

// PUT /api/pages/:slug — Edit a wiki page (immediate, synchronous save)
export async function PUT(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();
  const { content_markdown, change_summary } = body;

  if (!content_markdown || typeof content_markdown !== "string") {
    return NextResponse.json(
      { error: "content_markdown is required" },
      { status: 400 }
    );
  }

  // Atomic transaction: version snapshot + page update
  const result = await prisma.$transaction(async (tx) => {
    // 1. Get current page state
    const currentPage = await tx.page.findUnique({
      where: { slug: params.slug },
    });

    if (!currentPage) {
      throw new Error("Page not found");
    }

    const newVersionNumber = currentPage.versionNumber + 1;

    // 2. Create version record (snapshot of new state)
    await tx.version.create({
      data: {
        pageId: currentPage.id,
        versionNumber: newVersionNumber,
        contentMarkdown: content_markdown,
        sourceBlocks: currentPage.sourceBlocks, // preserve source citations
        origin: "manual-edit",
        changeSummary: change_summary || null,
      },
    });

    // 3. Update the page with new content — immediate, synchronous
    const updatedPage = await tx.page.update({
      where: { slug: params.slug },
      data: {
        contentMarkdown: content_markdown,
        versionNumber: newVersionNumber,
        origin: "manual-edit",
        lastModified: new Date(),
      },
    });

    return updatedPage;
  });

  // No buffering, no deferred writes — the transaction is committed.
  return NextResponse.json(result);
}
```

### 6c. Conflict Detection on Re-Ingestion

```python
# scripts/conflict_detection.py
"""
Conflict detection during re-ingestion.
Called when ingesting a document that may update an existing wiki page.
"""
import json
from typing import Optional
import psycopg2


def check_and_handle_conflict(
    cursor,
    page_id: str,
    incoming_markdown: str,
    incoming_source_blocks: str,
    doc_filename: str,
    ingestion_run_id: str,
) -> str:
    """
    Check if a page has been manually edited and handle accordingly.
    
    Returns:
        'updated' — page was updated directly (no manual edits existed)
        'conflict' — conflict flagged for user resolution
        'unchanged' — content hash matches, nothing to do
    """
    # Get current page state
    cursor.execute("""
        SELECT id, content_markdown, source_blocks, version_number, origin
        FROM pages WHERE id = %s
    """, (page_id,))
    page = cursor.fetchone()
    
    if not page:
        return 'unchanged'
    
    _, current_md, current_blocks, current_version, current_origin = page
    
    # Check if content actually changed
    if _content_hash(incoming_markdown) == _content_hash(current_md):
        return 'unchanged'
    
    # Check for manual edits in version history
    cursor.execute("""
        SELECT EXISTS(
            SELECT 1 FROM versions 
            WHERE page_id = %s AND origin IN ('manual-edit', 'conflict-resolution')
        )
    """, (page_id,))
    has_manual_edits = cursor.fetchone()[0]
    
    if has_manual_edits:
        # ═══════════════════════════════════════════════
        # CONFLICT PATH: Do NOT overwrite manual edits
        # ═══════════════════════════════════════════════
        
        # Store the incoming content for user review
        cursor.execute("""
            INSERT INTO pending_ingestions 
            (page_id, incoming_content_markdown, incoming_source_blocks,
             doc_filename, ingestion_run_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (page_id, incoming_markdown, incoming_source_blocks,
              doc_filename, ingestion_run_id))
        
        # Flag the page
        cursor.execute("""
            UPDATE pages SET conflict_status = 'pending' WHERE id = %s
        """, (page_id,))
        
        return 'conflict'
    else:
        # ═══════════════════════════════════════════════
        # SAFE PATH: No manual edits — update directly
        # ═══════════════════════════════════════════════
        
        new_version = current_version + 1
        
        # Create version snapshot
        cursor.execute("""
            INSERT INTO versions 
            (page_id, version_number, content_markdown, source_blocks,
             origin, change_summary)
            VALUES (%s, %s, %s, %s, 'ai-extracted', 
                    'Re-ingestion update from ' || %s)
        """, (page_id, new_version, incoming_markdown, 
              incoming_source_blocks, doc_filename))
        
        # Update page
        cursor.execute("""
            UPDATE pages 
            SET content_markdown = %s, source_blocks = %s,
                version_number = %s, last_modified = NOW(),
                origin = 'ai-extracted'
            WHERE id = %s
        """, (incoming_markdown, incoming_source_blocks, new_version, page_id))
        
        return 'updated'


def _content_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()
```

### 6d. Embedding and Retrieval

```python
# scripts/rebuild_index.py
"""
Vector index rebuild script.
Safe to re-run. Never touches relational data (pages, versions, source_chunks).
Only updates the embeddings table.

Usage:
    python scripts/rebuild_index.py

To update the Q&A system after edits or new document ingestion, run this script.
This rebuilds the vector index without affecting any wiki content or edit history.
"""
import os
import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer

# Configuration
DATABASE_URL = os.environ["DATABASE_URL"]
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
BATCH_SIZE = 64  # Embedding batch size


def rebuild_index():
    """
    Rebuild the entire vector index from current database state.
    
    1. Reads all source_chunks from PostgreSQL
    2. Reads all current wiki page content from pages table
    3. Generates embeddings using sentence-transformers
    4. Upserts into the embeddings table (pgvector)
    5. Logs the build to index_build_log
    """
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    model = SentenceTransformer(EMBEDDING_MODEL)
    
    build_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    
    # Log build start
    cursor.execute("""
        INSERT INTO index_build_log (id, started_at, status, embedding_model)
        VALUES (%s, %s, 'running', %s)
    """, (build_id, started_at, EMBEDDING_MODEL))
    conn.commit()
    
    try:
        chunks_indexed = 0
        pages_indexed = 0
        
        # ── Step 1: Embed source chunks ──
        cursor.execute("""
            SELECT id, text, doc_filename, heading_path, entity_name, section_type
            FROM source_chunks
            WHERE text IS NOT NULL AND length(text) > 10
        """)
        source_chunks = cursor.fetchall()
        
        print(f"Embedding {len(source_chunks)} source chunks...")
        
        for i in range(0, len(source_chunks), BATCH_SIZE):
            batch = source_chunks[i:i + BATCH_SIZE]
            texts = [row[1] for row in batch]
            embeddings = model.encode(texts, show_progress_bar=False)
            
            for row, embedding in zip(batch, embeddings):
                chunk_id, text, doc_filename, heading_path, entity_name, section_type = row
                content_hash = hashlib.sha256(text.encode()).hexdigest()
                
                metadata = json.dumps({
                    "doc_filename": doc_filename,
                    "heading_path": heading_path,
                    "entity_name": entity_name,
                    "section_type": section_type,
                })
                
                cursor.execute("""
                    INSERT INTO embeddings 
                    (source_type, source_id, chunk_text, content_hash, 
                     embedding, metadata)
                    VALUES ('source_chunk', %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (source_type, source_id, content_hash) 
                    DO UPDATE SET 
                        embedding = EXCLUDED.embedding,
                        chunk_text = EXCLUDED.chunk_text,
                        metadata = EXCLUDED.metadata,
                        created_at = NOW()
                """, (str(chunk_id), text, content_hash, 
                      embedding.tolist(), metadata))
                
                chunks_indexed += 1
            
            conn.commit()
            print(f"  Embedded {min(i + BATCH_SIZE, len(source_chunks))}/{len(source_chunks)} chunks")
        
        # ── Step 2: Embed wiki page sections ──
        cursor.execute("""
            SELECT id, slug, entity_name, content_markdown
            FROM pages
            WHERE content_markdown IS NOT NULL AND length(content_markdown) > 10
        """)
        pages = cursor.fetchall()
        
        print(f"Embedding {len(pages)} wiki pages...")
        
        for page_id, slug, entity_name, content_md in pages:
            # Split page into sections for more granular retrieval
            sections = _split_into_sections(content_md)
            
            for section_title, section_text in sections:
                if len(section_text.strip()) < 10:
                    continue
                
                # Prepend entity context for better retrieval
                embed_text = f"{entity_name} — {section_title}: {section_text}"
                content_hash = hashlib.sha256(embed_text.encode()).hexdigest()
                
                embedding = model.encode(embed_text)
                
                metadata = json.dumps({
                    "page_slug": slug,
                    "entity_name": entity_name,
                    "section_title": section_title,
                    "has_manual_edits": True,  # Conservative — mark all wiki pages
                })
                
                cursor.execute("""
                    INSERT INTO embeddings 
                    (source_type, source_id, chunk_text, content_hash,
                     embedding, metadata)
                    VALUES ('wiki_page_section', %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (source_type, source_id, content_hash)
                    DO UPDATE SET 
                        embedding = EXCLUDED.embedding,
                        chunk_text = EXCLUDED.chunk_text,
                        metadata = EXCLUDED.metadata,
                        created_at = NOW()
                """, (str(page_id), embed_text, content_hash,
                      embedding.tolist(), metadata))
            
            pages_indexed += 1
            conn.commit()
        
        # ── Step 3: Clean up orphaned embeddings ──
        cursor.execute("""
            DELETE FROM embeddings 
            WHERE source_type = 'source_chunk' 
            AND source_id::uuid NOT IN (SELECT id FROM source_chunks)
        """)
        cursor.execute("""
            DELETE FROM embeddings 
            WHERE source_type = 'wiki_page_section'
            AND source_id::uuid NOT IN (SELECT id FROM pages)
        """)
        
        # ── Step 4: Log build completion ──
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()
        
        cursor.execute("""
            UPDATE index_build_log 
            SET completed_at = %s, status = 'completed',
                chunks_indexed = %s, pages_indexed = %s, 
                duration_seconds = %s
            WHERE id = %s
        """, (completed_at, chunks_indexed, pages_indexed, duration, build_id))
        
        conn.commit()
        print(f"\n✓ Index rebuild complete:")
        print(f"  Chunks indexed: {chunks_indexed}")
        print(f"  Pages indexed:  {pages_indexed}")
        print(f"  Duration:       {duration:.1f}s")
        
    except Exception as e:
        cursor.execute("""
            UPDATE index_build_log 
            SET status = 'failed', error_message = %s, 
                completed_at = NOW()
            WHERE id = %s
        """, (str(e), build_id))
        conn.commit()
        raise
    finally:
        cursor.close()
        conn.close()


def _split_into_sections(markdown: str) -> list[tuple[str, str]]:
    """Split markdown content into (section_title, section_text) pairs."""
    sections = []
    current_title = "Overview"
    current_lines = []
    
    for line in markdown.split("\n"):
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    
    return sections


if __name__ == "__main__":
    rebuild_index()
```

### 6e. RAG Retrieval and Answer Generation

```typescript
// src/app/api/ask/route.ts
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import OpenAI from "openai";

// We call a Python embedding service or use a JS embedding library
// For simplicity, this example uses the OpenAI API for both embedding and answering
// In production, use sentence-transformers via a Python sidecar

export async function POST(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { question } = await request.json();

  if (!question || typeof question !== "string") {
    return NextResponse.json(
      { error: "question is required" },
      { status: 400 }
    );
  }

  // Step 1: Generate question embedding
  // (In production, use sentence-transformers matching the index model)
  const questionEmbedding = await generateEmbedding(question);

  // Step 2: Query pgvector for similar chunks
  const similarChunks = await prisma.$queryRaw`
    SELECT 
      source_type,
      source_id,
      chunk_text,
      metadata,
      1 - (embedding <=> ${questionEmbedding}::vector) as similarity
    FROM embeddings
    ORDER BY embedding <=> ${questionEmbedding}::vector
    LIMIT 10
  `;

  // Step 3: Build context with source attribution
  const contextParts = (similarChunks as any[]).map((chunk, i) => {
    const meta = chunk.metadata;
    const sourceLabel =
      chunk.source_type === "source_chunk"
        ? `[Source Document: ${meta.doc_filename}, §${(meta.heading_path || []).join(" > ")}]`
        : `[Wiki Page: ${meta.entity_name} — ${meta.section_title}${meta.has_manual_edits ? " (manually edited)" : ""}]`;

    return `--- Context ${i + 1} ${sourceLabel} ---\n${chunk.chunk_text}`;
  });

  const context = contextParts.join("\n\n");

  // Step 4: Generate answer with citations
  const openai = new OpenAI();
  const completion = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [
      {
        role: "system",
        content: `You are a lore expert assistant for a fictional world. Answer questions 
using ONLY the provided context. For every claim, cite the source using the labels 
provided (e.g., [Source Document: filename.docx, §Section] or [Wiki Page: Entity — Section]).

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
    max_tokens: 1000,
  });

  const answer = completion.choices[0].message.content;

  // Step 5: Get index staleness info
  const latestBuild = await prisma.indexBuildLog.findFirst({
    where: { status: "completed" },
    orderBy: { completedAt: "desc" },
  });

  const latestEdit = await prisma.page.findFirst({
    orderBy: { lastModified: "desc" },
    select: { lastModified: true },
  });

  const isStale =
    latestBuild?.completedAt && latestEdit?.lastModified
      ? latestEdit.lastModified > latestBuild.completedAt
      : true;

  return NextResponse.json({
    answer,
    sources: (similarChunks as any[]).map((c) => ({
      type: c.source_type,
      metadata: c.metadata,
      similarity: c.similarity,
      excerpt: c.chunk_text.substring(0, 200) + "...",
    })),
    index_staleness: {
      is_stale: isStale,
      last_built: latestBuild?.completedAt,
      latest_edit: latestEdit?.lastModified,
    },
  });
}

async function generateEmbedding(text: string): Promise<number[]> {
  // Option 1: Call a local Python service running sentence-transformers
  // Option 2: Use a JS embedding library like @xenova/transformers
  // Option 3: Use OpenAI embeddings (costs money but simpler)
  
  // Example using @xenova/transformers (runs locally, free):
  const { pipeline } = await import("@xenova/transformers");
  const extractor = await pipeline(
    "feature-extraction",
    "Xenova/all-MiniLM-L6-v2"
  );
  const output = await extractor(text, { pooling: "mean", normalize: true });
  return Array.from(output.data);
}
```

### 6f. Edit API Routes (Complete Set)

```typescript
// src/app/api/pages/[slug]/versions/route.ts
// GET /api/pages/:slug/versions — Get version history
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

export async function GET(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const page = await prisma.page.findUnique({
    where: { slug: params.slug },
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
      // Don't include full content in list view — fetch on demand
    },
  });

  return NextResponse.json(versions);
}


// src/app/api/pages/[slug]/versions/[versionId]/route.ts
// GET /api/pages/:slug/versions/:versionId — Get a specific version's content
export async function GET(
  request: NextRequest,
  { params }: { params: { slug: string; versionId: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const version = await prisma.version.findUnique({
    where: { id: params.versionId },
    include: {
      page: { select: { slug: true, entityName: true } },
    },
  });

  if (!version || version.page.slug !== params.slug) {
    return NextResponse.json({ error: "Version not found" }, { status: 404 });
  }

  return NextResponse.json(version);
}


// src/app/api/pages/[slug]/restore/route.ts
// POST /api/pages/:slug/restore — Restore a previous version
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

export async function POST(
  request: NextRequest,
  { params }: { params: { slug: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { version_id } = await request.json();

  if (!version_id) {
    return NextResponse.json(
      { error: "version_id is required" },
      { status: 400 }
    );
  }

  const result = await prisma.$transaction(async (tx) => {
    // 1. Get the target version
    const targetVersion = await tx.version.findUnique({
      where: { id: version_id },
    });

    if (!targetVersion) {
      throw new Error("Version not found");
    }

    // 2. Get current page
    const currentPage = await tx.page.findUnique({
      where: { slug: params.slug },
    });

    if (!currentPage || targetVersion.pageId !== currentPage.id) {
      throw new Error("Version does not belong to this page");
    }

    const newVersionNumber = currentPage.versionNumber + 1;

    // 3. Create a new version record (restore creates history, never deletes)
    await tx.version.create({
      data: {
        pageId: currentPage.id,
        versionNumber: newVersionNumber,
        contentMarkdown: targetVersion.contentMarkdown,
        sourceBlocks: targetVersion.sourceBlocks,
        origin: "restore",
        changeSummary: `Restored from version ${targetVersion.versionNumber}`,
      },
    });

    // 4. Update page to match restored version
    const updatedPage = await tx.page.update({
      where: { slug: params.slug },
      data: {
        contentMarkdown: targetVersion.contentMarkdown,
        sourceBlocks: targetVersion.sourceBlocks,
        versionNumber: newVersionNumber,
        origin: "restore",
        lastModified: new Date(),
      },
    });

    return updatedPage;
  });

  return NextResponse.json(result);
}


// src/app/api/pages/route.ts
// GET /api/pages — List all wiki pages (with filtering)
export async function GET(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const entityType = searchParams.get("type");
  const search = searchParams.get("q");
  const page = parseInt(searchParams.get("page") || "1");
  const limit = parseInt(searchParams.get("limit") || "50");

  const where: any = {};
  if (entityType) where.entityType = entityType;
  if (search) {
    where.OR = [
      { entityName: { contains: search, mode: "insensitive" } },
      { contentMarkdown: { contains: search, mode: "insensitive" } },
    ];
  }

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
}
```

---

## 7. Incremental Update Strategy

### Adding New Documents

When new `.docx` files are added to the corpus:

```bash
# 1. Place new .docx files in the data directory
cp new_document.docx data/docx/

# 2. Run the ingestion pipeline (appends only, never drops)
python scripts/ingest.py --input data/docx/new_document.docx

# 3. Rebuild the vector index to include new content in Q&A
python scripts/rebuild_index.py
```

### What Happens During Incremental Ingestion

1. **New entities** → New `pages` rows created with `origin = "ai-extracted"`
2. **Existing entities (no manual edits)** → Content appended, new version created with `origin = "ai-extracted"`
3. **Existing entities (has manual edits)** → **Conflict flagged**. Incoming content stored in `pending_ingestions`. Page shows conflict banner. User resolves manually.
4. **Duplicate content** → Detected via `content_hash` in `source_chunks`. Already-ingested blocks are skipped silently.

### Safety Guarantees

| Operation | Safe? | Details |
|-----------|-------|---------|
| Re-ingest same file | ✅ | Dedup via content_hash — no duplicates created |
| Ingest new file | ✅ | Only creates/appends — never drops |
| Re-ingest after manual edits | ✅ | Conflict flagged, manual edits preserved |
| Rebuild vector index | ✅ | Only touches embeddings table, never pages/versions |
| Database migration | ✅ | Prisma migrations are append-only |
| Server restart/redeploy | ✅ | All data in external PostgreSQL |

### What Is NEVER Done

- ❌ `DROP TABLE` or `TRUNCATE` on any table
- ❌ Overwriting manual edits without user confirmation
- ❌ Deleting version history
- ❌ Modifying source_chunks after initial insertion
- ❌ Storing any stateful data on the Vercel filesystem

---

## 8. Deployment & Security

### Option A: Vercel + Neon (Recommended for Remote Access)

```bash
# 1. Set up Neon database
# - Create account at neon.tech (free tier)
# - Create a project and database
# - Enable pgvector extension
# - Copy the connection string

# 2. Set environment variables on Vercel
NEXTAUTH_SECRET=<random-32-char-string>
NEXTAUTH_URL=https://your-app.vercel.app
DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/lorewiki?sslmode=require
WIKI_PASSWORD=<your-secret-wiki-password>

# 3. Deploy
vercel deploy --prod

# 4. Run initial database migration
npx prisma db push

# 5. Run ingestion pipeline (from your local machine, pointing at Neon)
DATABASE_URL=<neon-url> python scripts/ingest.py --input data/docx/
DATABASE_URL=<neon-url> python scripts/rebuild_index.py
```

### Option B: Docker Compose (Fully Offline/Local)

```yaml
# docker-compose.yml
version: "3.8"

services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://lorewiki:lorewiki@db:5432/lorewiki
      NEXTAUTH_SECRET: local-development-secret-change-in-prod
      NEXTAUTH_URL: http://localhost:3000
      OLLAMA_URL: http://ollama:11434
    depends_on:
      db:
        condition: service_healthy

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: lorewiki
      POSTGRES_PASSWORD: lorewiki
      POSTGRES_DB: lorewiki
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lorewiki"]
      interval: 5s
      timeout: 5s
      retries: 5

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"

volumes:
  pgdata:        # Persistent PostgreSQL data
  ollama_data:   # Persistent Ollama models
```

### Authentication

**For Vercel deployment:**
- NextAuth.js with a credentials provider (username/password)
- Single-user mode: one set of credentials stored in environment variables
- All API routes check `getServerSession()` — unauthenticated requests get 401
- Middleware protects all pages:

```typescript
// middleware.ts
export { default } from "next-auth/middleware";

export const config = {
  matcher: ["/((?!api/auth).*)"],  // Protect everything except auth endpoints
};
```

**For Docker deployment:**
- Same NextAuth.js approach, or simpler HTTP Basic Auth via nginx reverse proxy
- Network-level security: only bind to localhost or VPN

---

## 9. Persistence Verification Checklist

After initial deployment, verify persistence:

```bash
# 1. Create or ingest at least one wiki page
python scripts/ingest.py --input data/docx/test_document.docx

# 2. Edit a page manually via the UI

# 3. Redeploy the application
#    - Vercel: push a commit or run `vercel deploy --prod`
#    - Docker: `docker compose down && docker compose up -d`

# 4. Verify ALL of the following survived:
#    ☐ All wiki pages are present and unchanged
#    ☐ Manual edits are preserved exactly
#    ☐ Version history shows all previous versions
#    ☐ Source chunks are intact
#    ☐ Embeddings are queryable (test a Q&A question)
#    ☐ Index build log shows previous build records
#    ☐ Cross-links still function

# 5. If ANY of the above failed, the deployment has an
#    ephemeral storage bug that must be fixed before proceeding.
```

---

## Appendix A: LLM Usage Boundaries (Quick Reference)

| Task | LLM Used? | What LLM Does | What LLM Does NOT Do |
|------|-----------|---------------|---------------------|
| Parse .docx | ❌ | N/A — deterministic `python-docx` | — |
| Identify entity names | ✅ | Classifies: returns entity name string | Does not write page content |
| Classify entity type | ✅ | Returns enum label (character, location, etc.) | Does not describe the entity |
| Route to section | ✅ | Returns section label (overview, history, etc.) | Does not summarize or rewrite |
| Generate wiki page content | ❌ | N/A — content is copied verbatim from blocks | **Never generates prose for wiki** |
| Cross-link generation | ❌ | N/A — deterministic string matching | — |
| Q&A answer generation | ✅ | Synthesizes, reasons, cites from context | **Exempt** from source fidelity |
| Entity deduplication | ✅ | Determines if two names refer to same entity | Does not merge content |

---

## Appendix B: Cost Analysis (Free Tier Viability)

| Service | Free Tier Limits | Expected Usage | Fits? |
|---------|-----------------|----------------|-------|
| **Neon** | 0.5 GB storage, 190 compute hours/mo | ~100MB for 10 docs + embeddings | ✅ |
| **Vercel** | 100 GB bandwidth, serverless functions | Light personal use | ✅ |
| **sentence-transformers** | Unlimited (runs locally) | Batch embedding during rebuild | ✅ |
| **Ollama** | Unlimited (runs locally) | Classification during ingestion | ✅ |
| **OpenAI gpt-4o-mini** | $0.15/1M input tokens | ~$1-2 for full corpus classification | ✅ (~free) |

Total cost for a personal wiki: **$0–$2/month** (effectively free).

---

*End of specification.*
