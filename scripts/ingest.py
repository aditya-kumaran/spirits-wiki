"""
Main ingestion script.
Parses .docx files, classifies entities, and stores verbatim content in the database.

Usage:
    python scripts/ingest.py                          # Ingest all files in wikiInitializationDocuments/
    python scripts/ingest.py --file path/to/doc.docx  # Ingest a specific file

All wiki page content is extracted VERBATIM from .docx files.
The LLM is used ONLY as a classifier (entity name, type, section routing).
"""
import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json
from groq import Groq

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))

from config import DATABASE_URL, GROQ_API_KEY, GROQ_MODEL, DOCX_DIR, MIN_CONFIDENCE, MIN_TEXT_LENGTH
from parse_docx import parse_docx, ContentBlock, ExtractedImage
from classify_entities import classify_block, EntityClassification


def slugify(name: str) -> str:
    """Create a URL-safe slug from an entity name."""
    slug = name.lower().strip()
    slug = slug.replace("'", "").replace('"', "").replace("'", "").replace(""", "").replace(""", "")
    slug = "".join(c if c.isalnum() or c in (" ", "-") else "" for c in slug)
    slug = slug.replace(" ", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:100]


def assemble_markdown(items: list) -> str:
    """
    Assemble wiki page markdown from classified blocks.
    ALL TEXT IS VERBATIM from the .docx -- no LLM-generated prose.
    """
    sections: dict = {}
    for block, classification in items:
        section = classification.section_type
        if section not in sections:
            sections[section] = []
        sections[section].append((block, classification))

    all_sections = [
        "overview", "attributes", "relationships", "history",
        "appearances", "abilities", "culture", "geography",
        "timeline", "other"
    ]

    lines = []
    for section_name in all_sections:
        display_name = section_name.replace("_", " ").title()
        lines.append(f"## {display_name}")
        lines.append("")

        if section_name in sections:
            for block, classification in sections[section_name]:
                lines.append(block.text)
                lines.append("")
                heading_str = " > ".join(block.heading_path) if block.heading_path else "N/A"
                lines.append(f"*[Source: {block.doc_filename}, §{heading_str}]*")
                lines.append("")
        else:
            lines.append("*Not documented in source materials*")
            lines.append("")

    return "\n".join(lines)


def assemble_source_blocks_json(items: list) -> str:
    """Build the source_blocks JSON array."""
    blocks = []
    for block, classification in items:
        blocks.append({
            "text": block.text,
            "source_doc": block.doc_filename,
            "heading_path": block.heading_path,
            "paragraph_index": block.paragraph_index,
            "content_hash": block.content_hash,
            "section_type": classification.section_type,
        })
    return json.dumps(blocks)


def ingest_document(file_path: Path, conn, llm_client: Groq):
    """Ingest a single .docx file into the database."""
    ingestion_run_id = str(uuid.uuid4())
    file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

    print(f"\n{'='*60}")
    print(f"Ingesting: {file_path.name}")
    print(f"File hash: {file_hash[:16]}...")
    print(f"Run ID: {ingestion_run_id[:8]}...")

    # Check if already ingested with same hash
    cursor = conn.cursor()
    cursor.execute("SELECT file_hash FROM documents WHERE filename = %s", (file_path.name,))
    existing = cursor.fetchone()
    if existing and existing[0] == file_hash:
        print(f"  Skipping: file unchanged since last ingestion")
        return

    # Step 1: Parse .docx
    print(f"  Parsing document...")
    blocks, images = parse_docx(file_path)
    print(f"  Extracted {len(blocks)} text blocks and {len(images)} images")

    # Step 2: Classify blocks
    print(f"  Classifying entities (this may take a while)...")
    classified_blocks = []
    for i, block in enumerate(blocks):
        if len(block.text.strip()) < MIN_TEXT_LENGTH:
            continue
        if block.block_type == "heading" and len(block.text.split()) <= 5:
            continue

        classification = classify_block(block, llm_client, GROQ_MODEL)
        if classification and classification.confidence >= MIN_CONFIDENCE:
            classified_blocks.append((block, classification))

        if (i + 1) % 50 == 0:
            print(f"    Classified {i+1}/{len(blocks)} blocks ({len(classified_blocks)} entities found)")

        # Rate limiting for Groq
        if (i + 1) % 28 == 0:
            import time
            time.sleep(3)

    print(f"  Classified {len(classified_blocks)} blocks to entities")

    # Step 3: Group by entity
    entity_blocks: dict = {}
    for block, classification in classified_blocks:
        entity_name = classification.primary_entity
        if entity_name not in entity_blocks:
            entity_blocks[entity_name] = []
        entity_blocks[entity_name].append((block, classification))

    print(f"  Found {len(entity_blocks)} distinct entities")

    # Step 4: Store in database
    cursor.execute("""
        INSERT INTO documents (id, filename, file_hash, chunk_count, ingestion_status)
        VALUES (%s, %s, %s, %s, 'completed')
        ON CONFLICT (filename) DO UPDATE
        SET file_hash = EXCLUDED.file_hash,
            chunk_count = EXCLUDED.chunk_count,
            last_ingested_at = NOW(),
            ingestion_status = 'completed'
    """, (str(uuid.uuid4()), file_path.name, file_hash, len(classified_blocks)))

    pages_created = 0
    pages_updated = 0
    conflicts_found = 0

    for entity_name, items in entity_blocks.items():
        if not entity_name or entity_name.lower() in ("unknown", "n/a", "none"):
            continue

        entity_type = items[0][1].entity_type
        slug = slugify(entity_name)
        if not slug:
            continue

        # Check if page exists
        cursor.execute("SELECT id, origin, version_number FROM pages WHERE slug = %s", (slug,))
        existing_page = cursor.fetchone()

        content_md = assemble_markdown(items)
        source_blocks_json = assemble_source_blocks_json(items)

        if existing_page:
            page_id, current_origin, current_version = existing_page

            # Check for manual edits
            cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM versions
                    WHERE page_id = %s AND origin IN ('manual-edit', 'conflict-resolution')
                )
            """, (page_id,))
            has_manual_edits = cursor.fetchone()[0]

            if has_manual_edits:
                # CONFLICT: store as pending
                cursor.execute("""
                    INSERT INTO pending_ingestions
                    (id, page_id, incoming_content_markdown, incoming_source_blocks,
                     doc_filename, ingestion_run_id)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                """, (str(uuid.uuid4()), page_id, content_md,
                      source_blocks_json, file_path.name, ingestion_run_id))
                cursor.execute(
                    "UPDATE pages SET conflict_status = 'pending' WHERE id = %s",
                    (page_id,)
                )
                conflicts_found += 1
                print(f"    Conflict: {entity_name}")
            else:
                # Append new content
                new_version = current_version + 1
                cursor.execute("SELECT content_markdown FROM pages WHERE id = %s", (page_id,))
                current_md = cursor.fetchone()[0]

                merged_md = current_md + "\n\n---\n\n" + content_md

                cursor.execute("""
                    INSERT INTO versions (id, page_id, version_number, content_markdown,
                        source_blocks, origin, change_summary)
                    VALUES (%s, %s, %s, %s, %s::jsonb, 'ai-extracted',
                        %s)
                """, (str(uuid.uuid4()), page_id, new_version, merged_md,
                      source_blocks_json, f"Re-ingestion from {file_path.name}"))

                cursor.execute("""
                    UPDATE pages SET content_markdown = %s, source_blocks = %s::jsonb,
                        version_number = %s, last_modified = NOW()
                    WHERE id = %s
                """, (merged_md, source_blocks_json, new_version, page_id))
                pages_updated += 1
        else:
            # Create new page
            page_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO pages (id, slug, entity_name, entity_type, content_markdown,
                    source_blocks, version_number, origin)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, 1, 'ai-extracted')
            """, (page_id, slug, entity_name, entity_type, content_md, source_blocks_json))

            cursor.execute("""
                INSERT INTO versions (id, page_id, version_number, content_markdown,
                    source_blocks, origin, change_summary)
                VALUES (%s, %s, 1, %s, %s::jsonb, 'ai-extracted',
                    'Initial extraction from source documents')
            """, (str(uuid.uuid4()), page_id, content_md, source_blocks_json))
            pages_created += 1

        # Store source chunks
        for block, classification in items:
            try:
                cursor.execute("""
                    INSERT INTO source_chunks
                    (id, doc_filename, heading_path, paragraph_index, block_type,
                     text, content_hash, entity_name, entity_type, section_type,
                     confidence, page_id, ingestion_run_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (doc_filename, paragraph_index, content_hash) DO NOTHING
                """, (
                    str(uuid.uuid4()),
                    block.doc_filename, block.heading_path, block.paragraph_index,
                    block.block_type, block.text, block.content_hash,
                    classification.primary_entity, classification.entity_type,
                    classification.section_type, classification.confidence,
                    page_id, ingestion_run_id,
                ))
            except Exception as e:
                print(f"    Warning: Failed to store chunk: {e}")

    conn.commit()

    print(f"\n  Results:")
    print(f"    Pages created:    {pages_created}")
    print(f"    Pages updated:    {pages_updated}")
    print(f"    Conflicts found:  {conflicts_found}")
    print(f"    Images extracted: {len(images)}")

    # Store images (save to disk for now, upload separately)
    if images:
        img_dir = os.path.join(os.path.dirname(__file__), "..", "data", "extracted_images")
        os.makedirs(img_dir, exist_ok=True)
        for img in images:
            img_path = os.path.join(img_dir, img.filename)
            with open(img_path, "wb") as f:
                f.write(img.image_bytes)
        print(f"    Images saved to: {img_dir}")


def main():
    parser = argparse.ArgumentParser(description="Ingest .docx files into the wiki database")
    parser.add_argument("--file", type=str, help="Path to a specific .docx file to ingest")
    args = parser.parse_args()

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable is not set")
        sys.exit(1)
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY environment variable is not set")
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    llm_client = Groq(api_key=GROQ_API_KEY)

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}")
            sys.exit(1)
        ingest_document(file_path, conn, llm_client)
    else:
        docx_dir = Path(DOCX_DIR)
        if not docx_dir.exists():
            print(f"ERROR: Document directory not found: {docx_dir}")
            sys.exit(1)

        docx_files = sorted(docx_dir.glob("*.docx"))
        if not docx_files:
            print(f"No .docx files found in {docx_dir}")
            sys.exit(0)

        print(f"Found {len(docx_files)} .docx files to ingest:")
        for f in docx_files:
            print(f"  - {f.name} ({f.stat().st_size / 1024 / 1024:.1f} MB)")

        for file_path in docx_files:
            try:
                ingest_document(file_path, conn, llm_client)
            except Exception as e:
                print(f"\n  ERROR ingesting {file_path.name}: {e}")
                import traceback
                traceback.print_exc()
                conn.rollback()

    conn.close()
    print(f"\nIngestion complete!")


if __name__ == "__main__":
    main()
