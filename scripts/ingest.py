"""
Main ingestion script.
Parses .docx files, classifies entities, and stores synthesized content in the database.

Usage:
    python scripts/ingest.py                          # Ingest all files in wikiInitializationDocuments/
    python scripts/ingest.py --file path/to/doc.docx  # Ingest a specific file
    python scripts/ingest.py --min-blocks 3           # Require 3+ blocks per entity (default: 2)
    python scripts/ingest.py --no-checkpoint          # Ignore checkpoint and start fresh

Content is synthesized by the LLM from source material, with mandatory
footnote citations linking every claim back to the exact source text.

Classification progress is checkpointed to disk so interrupted runs can resume.
Checkpoints are versioned — any change to the ingestion or classification scripts
automatically invalidates old checkpoints.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))

from config import DATABASE_URL, LLM_PROVIDER, DOCX_DIR, MIN_CONFIDENCE, MIN_TEXT_LENGTH
from parse_docx import parse_docx, ContentBlock, ExtractedImage
from classify_entities import classify_block, EntityClassification
from synthesize_content import synthesize_wiki_page
from llm_client import create_llm_client, LLMClient

# Directory for checkpoint files
CHECKPOINT_DIR = os.path.join(os.path.dirname(__file__), ".checkpoints")


def compute_script_version() -> str:
    """
    Compute a hash of all key script files. Any change to these files
    invalidates existing checkpoints, forcing a fresh classification.
    """
    scripts_dir = os.path.dirname(__file__)
    version_files = [
        "ingest.py", "classify_entities.py", "synthesize_content.py",
        "parse_docx.py", "llm_client.py", "config.py",
    ]
    h = hashlib.sha256()
    for fname in sorted(version_files):
        fpath = os.path.join(scripts_dir, fname)
        if os.path.exists(fpath):
            h.update(open(fpath, "rb").read())
    return h.hexdigest()[:16]


def get_checkpoint_path(file_path: Path) -> str:
    """Get the checkpoint file path for a given document."""
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    safe_name = file_path.name.replace(" ", "_").replace(".", "_")
    return os.path.join(CHECKPOINT_DIR, f"classify_{safe_name}.json")


def load_checkpoint(file_path: Path, file_hash: str) -> tuple[list, int]:
    """
    Load classification checkpoint if valid.
    Returns (classified_blocks_data, last_processed_index).
    Returns ([], -1) if no valid checkpoint exists.
    """
    cp_path = get_checkpoint_path(file_path)
    if not os.path.exists(cp_path):
        return [], -1

    try:
        with open(cp_path, "r") as f:
            data = json.load(f)

        # Validate checkpoint matches current script version and file
        if data.get("script_version") != compute_script_version():
            print("  Checkpoint found but script version changed — starting fresh")
            os.remove(cp_path)
            return [], -1

        if data.get("file_hash") != file_hash:
            print("  Checkpoint found but file content changed — starting fresh")
            os.remove(cp_path)
            return [], -1

        last_idx = data.get("last_processed_index", -1)
        blocks_data = data.get("classified_blocks", [])
        print(f"  Resuming from checkpoint: {last_idx + 1} blocks already classified ({len(blocks_data)} matched)")
        return blocks_data, last_idx

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"  Checkpoint corrupted ({e}) — starting fresh")
        if os.path.exists(cp_path):
            os.remove(cp_path)
        return [], -1


def save_checkpoint(file_path: Path, file_hash: str, classified_data: list, last_index: int):
    """Save classification progress to a checkpoint file."""
    cp_path = get_checkpoint_path(file_path)
    data = {
        "script_version": compute_script_version(),
        "file_hash": file_hash,
        "file_name": file_path.name,
        "last_processed_index": last_index,
        "classified_blocks": classified_data,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    # Write atomically (write to temp, then rename)
    tmp_path = cp_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    os.replace(tmp_path, cp_path)


def delete_checkpoint(file_path: Path):
    """Remove checkpoint after successful ingestion."""
    cp_path = get_checkpoint_path(file_path)
    if os.path.exists(cp_path):
        os.remove(cp_path)


def serialize_classification(block: ContentBlock, classification: EntityClassification) -> dict:
    """Serialize a (block, classification) pair for checkpoint storage."""
    return {
        "block": {
            "doc_filename": block.doc_filename,
            "heading_path": block.heading_path,
            "paragraph_index": block.paragraph_index,
            "text": block.text,
            "style": getattr(block, "style", ""),
            "block_type": block.block_type,
            "content_hash": block.content_hash,
            "parent_context": getattr(block, "parent_context", ""),
            "indent_level": getattr(block, "indent_level", 0),
        },
        "classification": {
            "primary_entity": classification.primary_entity,
            "entity_type": classification.entity_type,
            "section_type": classification.section_type,
            "mentioned_entities": classification.mentioned_entities,
            "confidence": classification.confidence,
            "relevant_entities": classification.relevant_entities,
        },
    }


def deserialize_classification(data: dict) -> tuple:
    """Reconstruct (ContentBlock, EntityClassification) from checkpoint data."""
    b = data["block"]
    c = data["classification"]
    block = ContentBlock(
        doc_filename=b["doc_filename"],
        heading_path=b["heading_path"],
        paragraph_index=b["paragraph_index"],
        text=b["text"],
        style=b.get("style", ""),
        block_type=b["block_type"],
    )
    # Restore optional attributes
    block.parent_context = b.get("parent_context", "")
    block.indent_level = b.get("indent_level", 0)
    classification = EntityClassification(
        primary_entity=c["primary_entity"],
        entity_type=c["entity_type"],
        section_type=c["section_type"],
        mentioned_entities=c["mentioned_entities"],
        confidence=c["confidence"],
        relevant_entities=c["relevant_entities"],
    )
    return block, classification


def get_db_connection():
    """Create a fresh database connection."""
    return psycopg2.connect(DATABASE_URL)


def slugify(name: str) -> str:
    """Create a URL-safe slug from an entity name."""
    slug = name.lower().strip()
    slug = slug.replace("'", "").replace('"', "").replace("\u2019", "").replace("\u201c", "").replace("\u201d", "")
    slug = "".join(c if c.isalnum() or c in (" ", "-") else "" for c in slug)
    slug = slug.replace(" ", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:100]


def is_proper_noun_entity(name: str) -> bool:
    """
    Filter out generic/non-entity terms and pronouns.
    Returns True only for names that look like proper nouns.
    """
    if not name or len(name) < 2:
        return False

    # Reject pronouns — these should never become entity pages
    pronouns = {
        "he", "him", "his", "himself",
        "she", "her", "hers", "herself",
        "they", "them", "their", "theirs", "themselves",
        "it", "its", "itself",
        "we", "us", "our", "ours", "ourselves",
        "i", "me", "my", "mine", "myself",
        "you", "your", "yours", "yourself", "yourselves",
    }
    if name.lower().strip() in pronouns:
        return False

    # Reject single common words
    common_words = {
        "unknown", "n/a", "none", "other", "general", "various",
        "introduction", "overview", "summary", "conclusion", "chapter",
        "section", "note", "notes", "description", "the", "this",
        "that", "these", "those", "here", "there", "world", "story",
        "character", "location", "event", "history", "philosophy",
        "culture", "religion", "magic", "power", "system", "land",
        "people", "group", "place", "time", "era", "age", "type",
        "example", "list", "table", "figure", "appendix", "reference",
        "document", "page", "text", "content", "heading", "paragraph",
    }
    if name.lower().strip() in common_words:
        return False

    # Reject names that are all lowercase (likely generic terms)
    # But allow names with mixed case or all caps
    words = name.split()
    if len(words) == 1 and name[0].islower():
        return False

    # Reject very long "names" that are actually sentences
    if len(words) > 6:
        return False

    return True


def assemble_source_blocks_json(items: list) -> str:
    """Build the source_blocks JSON array for storage."""
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


def extract_wiki_links(content_md: str) -> list:
    """Extract [[Entity Name]] links from markdown content."""
    return re.findall(r'\[\[([^\]]+)\]\]', content_md)


def store_entity_page(entity_name, entity_type, items, file_path, ingestion_run_id, llm_client, is_local_llm=False):
    """
    Store a single entity's page in the database.
    Synthesizes content using LLM with citations.
    Opens a fresh connection per entity for resilience.

    When a page already exists (from a previous file), this MERGES the new
    source blocks with the existing ones and re-synthesizes from all blocks
    combined, so information from multiple files accumulates on one page.
    """
    slug = slugify(entity_name)
    if not slug:
        return "skipped", None

    # First, check if the page exists and get existing source blocks for merging
    conn = get_db_connection()
    existing_page = None
    existing_blocks_data = []
    has_manual_edits = False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, origin, version_number, source_blocks FROM pages WHERE slug = %s", (slug,))
        row = cursor.fetchone()
        if row:
            existing_page = {"id": row[0], "origin": row[1], "version_number": row[2]}
            existing_blocks_data = json.loads(row[3]) if row[3] else []

            cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM versions
                    WHERE page_id = %s AND origin IN ('manual-edit', 'conflict-resolution')
                )
            """, (existing_page["id"],))
            has_manual_edits = cursor.fetchone()[0]
    finally:
        conn.close()

    # Build the combined set of source blocks for synthesis
    all_items = list(items)  # Start with new blocks

    if existing_page and existing_blocks_data and not has_manual_edits:
        # Merge: collect existing block hashes to avoid duplicates
        new_hashes = {block.content_hash for block, _ in items}
        existing_kept = 0
        for eb in existing_blocks_data:
            if eb.get("content_hash") not in new_hashes:
                # Create a lightweight stand-in for existing blocks
                existing_kept += 1
                # We need block + classification pairs for synthesis
                # Create minimal objects from stored JSON
                from parse_docx import ContentBlock
                from classify_entities import EntityClassification
                fake_block = ContentBlock(
                    doc_filename=eb.get("source_doc", "unknown"),
                    heading_path=eb.get("heading_path", []),
                    paragraph_index=eb.get("paragraph_index", 0),
                    text=eb.get("text", ""),
                    style="",
                    block_type=eb.get("block_type", "paragraph"),
                )
                fake_classification = EntityClassification(
                    primary_entity=entity_name,
                    entity_type=entity_type,
                    section_type=eb.get("section_type", "other"),
                    mentioned_entities=[],
                    confidence=0.9,
                    relevant_entities=[entity_name],
                )
                all_items.append((fake_block, fake_classification))
        if existing_kept > 0:
            print(f"      Merging {existing_kept} existing blocks + {len(items)} new blocks")

    # Synthesize wiki content with citations from ALL blocks
    print(f"    Synthesizing: {entity_name} ({len(all_items)} total blocks)...")
    content_md, metadata = synthesize_wiki_page(entity_name, entity_type, all_items, llm_client)
    source_blocks_json = assemble_source_blocks_json(all_items)
    metadata_json = json.dumps(metadata) if metadata else "{}"

    # Rate limit between synthesis calls (only needed for cloud APIs)
    if not is_local_llm:
        time.sleep(2)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        result = "created"

        if existing_page:
            page_id = existing_page["id"]
            current_version = existing_page["version_number"]

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
                result = "conflict"
            else:
                # Update with merged + re-synthesized content
                new_version = current_version + 1
                cursor.execute("""
                    INSERT INTO versions (id, page_id, version_number, content_markdown,
                        source_blocks, origin, change_summary)
                    VALUES (%s, %s, %s, %s, %s::jsonb, 'ai-extracted',
                        %s)
                """, (str(uuid.uuid4()), page_id, new_version, content_md,
                      source_blocks_json, f"Merged content from {file_path.name}"))

                cursor.execute("""
                    UPDATE pages SET content_markdown = %s, source_blocks = %s::jsonb,
                        metadata = %s::jsonb, version_number = %s, last_modified = NOW()
                    WHERE id = %s
                """, (content_md, source_blocks_json, metadata_json, new_version, page_id))
                result = "updated"
        else:
            # Create new page
            page_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO pages (id, slug, entity_name, entity_type, content_markdown,
                    source_blocks, metadata, version_number, origin)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, 1, 'ai-extracted')
            """, (page_id, slug, entity_name, entity_type, content_md, source_blocks_json, metadata_json))

            cursor.execute("""
                INSERT INTO versions (id, page_id, version_number, content_markdown,
                    source_blocks, origin, change_summary)
                VALUES (%s, %s, 1, %s, %s::jsonb, 'ai-extracted',
                    'Initial extraction from source documents')
            """, (str(uuid.uuid4()), page_id, content_md, source_blocks_json))
            result = "created"

        # Store source chunks (only new ones — existing ones are already stored)
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
                conn.rollback()
                conn = get_db_connection()
                cursor = conn.cursor()

        conn.commit()
        return result, page_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def generate_cross_links(entity_blocks: dict, page_ids: dict):
    """
    Generate cross-links between entity pages based on:
    1. mentioned_entities from classification
    2. [[wiki links]] in synthesized content
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        links_created = 0

        # Build a lookup: entity name -> slug
        name_to_slug = {}
        for entity_name in entity_blocks:
            slug = slugify(entity_name)
            if slug:
                name_to_slug[entity_name.lower()] = slug

        for entity_name, items in entity_blocks.items():
            source_slug = slugify(entity_name)
            if not source_slug or source_slug not in page_ids:
                continue

            source_page_id = page_ids[source_slug]
            linked_targets = set()

            # Collect mentioned entities from classification
            for block, classification in items:
                for mentioned in classification.mentioned_entities:
                    mentioned_lower = mentioned.lower()
                    if mentioned_lower in name_to_slug:
                        target_slug = name_to_slug[mentioned_lower]
                        if target_slug != source_slug and target_slug in page_ids:
                            linked_targets.add(target_slug)

            # Create cross-link records
            for target_slug in linked_targets:
                target_page_id = page_ids[target_slug]
                try:
                    cursor.execute("""
                        INSERT INTO cross_links (id, source_page_id, target_page_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (source_page_id, target_page_id) DO NOTHING
                    """, (str(uuid.uuid4()), source_page_id, target_page_id))
                    links_created += 1
                except Exception:
                    pass

        conn.commit()
        return links_created
    finally:
        conn.close()


def ingest_document(file_path: Path, llm_client: LLMClient, min_blocks: int = 2, is_local_llm: bool = False, use_checkpoint: bool = True):
    """Ingest a single .docx file into the database."""
    ingestion_run_id = str(uuid.uuid4())
    file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

    print(f"\n{'='*60}")
    print(f"Ingesting: {file_path.name}")
    print(f"File hash: {file_hash[:16]}...")
    print(f"Script version: {compute_script_version()}")
    print(f"Run ID: {ingestion_run_id[:8]}...")
    print(f"Min blocks per entity: {min_blocks}")

    # Check if already ingested with same hash (fresh connection)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT file_hash FROM documents WHERE filename = %s", (file_path.name,))
        existing = cursor.fetchone()
        if existing and existing[0] == file_hash:
            print(f"  Skipping: file unchanged since last ingestion")
            return
    finally:
        conn.close()

    # Step 1: Parse .docx (no DB needed)
    print(f"  Parsing document...")
    blocks, images = parse_docx(file_path)
    print(f"  Extracted {len(blocks)} text blocks and {len(images)} images")

    # Step 2: Classify blocks (no DB needed — only LLM calls)
    # Try loading checkpoint for resume support
    checkpoint_data = []
    resume_from = -1
    if use_checkpoint:
        checkpoint_data, resume_from = load_checkpoint(file_path, file_hash)

    # Reconstruct already-classified blocks from checkpoint
    classified_blocks = []
    if checkpoint_data:
        for cd in checkpoint_data:
            try:
                classified_blocks.append(deserialize_classification(cd))
            except (KeyError, TypeError) as e:
                print(f"  Warning: skipping corrupted checkpoint entry: {e}")

    if resume_from >= 0 and resume_from >= len(blocks) - 1:
        print(f"  Classification already complete from checkpoint ({len(classified_blocks)} matched)")
    else:
        start_from = resume_from + 1 if resume_from >= 0 else 0
        if start_from > 0:
            print(f"  Resuming classification from block {start_from}...")
        else:
            print(f"  Classifying entities (this may take a while)...")

        for i in range(start_from, len(blocks)):
            block = blocks[i]
            if len(block.text.strip()) < MIN_TEXT_LENGTH:
                pass  # Skip but still count as processed for checkpoint
            elif block.block_type == "heading" and len(block.text.split()) <= 5:
                pass  # Skip headings with <= 5 words
            else:
                classification = classify_block(block, llm_client)
                if classification and classification.confidence >= MIN_CONFIDENCE:
                    classified_blocks.append((block, classification))
                    checkpoint_data.append(serialize_classification(block, classification))

            if (i + 1) % 50 == 0:
                print(f"    Classified {i+1}/{len(blocks)} blocks ({len(classified_blocks)} matched)")
                # Save checkpoint every 50 blocks
                if use_checkpoint:
                    save_checkpoint(file_path, file_hash, checkpoint_data, i)

            # Rate limiting (only needed for cloud APIs like Groq)
            if not is_local_llm and (i + 1 - start_from) > 0 and (i + 1 - start_from) % 28 == 0:
                time.sleep(3)

        # Final checkpoint save
        if use_checkpoint:
            save_checkpoint(file_path, file_hash, checkpoint_data, len(blocks) - 1)

    print(f"  Classified {len(classified_blocks)} blocks to entities")

    # Step 3: Group by entity using multi-entity attribution
    # A single block can be relevant to multiple entities (e.g., "she injured him"
    # is relevant to both Catherine and Jacob). We use relevant_entities from the
    # classifier to attribute blocks to all entities they contain info about.
    entity_blocks: dict = {}
    for block, classification in classified_blocks:
        # Get all entities this block is relevant to
        relevant = getattr(classification, 'relevant_entities', None) or []
        if not relevant:
            # Fallback: just use primary_entity
            relevant = [classification.primary_entity]

        for entity_name in relevant:
            if not entity_name or entity_name.lower() in ("unknown", "n/a", "none"):
                continue
            if entity_name not in entity_blocks:
                entity_blocks[entity_name] = []
            entity_blocks[entity_name].append((block, classification))

    # Step 4: FILTER — only keep entities with enough blocks AND proper noun names
    filtered_entities = {}
    skipped_too_few = 0
    skipped_not_proper = 0

    for entity_name, items in entity_blocks.items():
        if not entity_name or entity_name.lower() in ("unknown", "n/a", "none"):
            continue

        if not is_proper_noun_entity(entity_name):
            skipped_not_proper += 1
            continue

        if len(items) < min_blocks:
            skipped_too_few += 1
            continue

        filtered_entities[entity_name] = items

    print(f"  Found {len(entity_blocks)} raw entities")
    print(f"  Filtered to {len(filtered_entities)} entities (skipped {skipped_too_few} with <{min_blocks} blocks, {skipped_not_proper} non-proper-nouns)")

    # Step 5: Record the document (fresh connection)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (id, filename, file_hash, chunk_count, ingestion_status)
            VALUES (%s, %s, %s, %s, 'completed')
            ON CONFLICT (filename) DO UPDATE
            SET file_hash = EXCLUDED.file_hash,
                chunk_count = EXCLUDED.chunk_count,
                last_ingested_at = NOW(),
                ingestion_status = 'completed'
        """, (str(uuid.uuid4()), file_path.name, file_hash, len(classified_blocks)))
        conn.commit()
    finally:
        conn.close()

    # Step 6: Synthesize and store each entity page
    pages_created = 0
    pages_updated = 0
    conflicts_found = 0
    errors = 0
    page_ids = {}  # slug -> page_id for cross-linking

    total = len(filtered_entities)
    for idx, (entity_name, items) in enumerate(filtered_entities.items()):
        entity_type = items[0][1].entity_type

        try:
            result, page_id = store_entity_page(
                entity_name, entity_type, items, file_path,
                ingestion_run_id, llm_client, is_local_llm
            )
            slug = slugify(entity_name)
            if page_id:
                page_ids[slug] = page_id

            if result == "created":
                pages_created += 1
            elif result == "updated":
                pages_updated += 1
            elif result == "conflict":
                conflicts_found += 1
                print(f"    Conflict: {entity_name}")
        except Exception as e:
            errors += 1
            print(f"    ERROR storing '{entity_name}': {e}")

        if (idx + 1) % 10 == 0 or (idx + 1) == total:
            print(f"    Progress: {idx+1}/{total} entities stored...")

    # Step 7: Generate cross-links
    print(f"  Generating cross-links...")
    # Also need existing page IDs for cross-linking
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT slug, id FROM pages")
        for row in cursor.fetchall():
            if row[0] not in page_ids:
                page_ids[row[0]] = row[1]
    finally:
        conn.close()

    links_created = generate_cross_links(filtered_entities, page_ids)

    # Clean up checkpoint after successful ingestion
    if use_checkpoint:
        delete_checkpoint(file_path)
        print(f"  Checkpoint cleaned up (ingestion complete)")

    print(f"\n  Results:")
    print(f"    Pages created:    {pages_created}")
    print(f"    Pages updated:    {pages_updated}")
    print(f"    Conflicts found:  {conflicts_found}")
    print(f"    Cross-links:      {links_created}")
    print(f"    Errors:           {errors}")
    print(f"    Images extracted: {len(images)}")

    # Store images to disk
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
    parser.add_argument("--min-blocks", type=int, default=2,
                        help="Minimum number of source blocks for an entity to get a page (default: 2)")
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="Ignore any existing checkpoint and start classification from scratch")
    args = parser.parse_args()
    use_checkpoint = not args.no_checkpoint

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable is not set")
        sys.exit(1)

    # Verify DB connectivity before starting
    try:
        conn = get_db_connection()
        conn.close()
        print("Database connection verified.")
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}")
        sys.exit(1)

    # Create LLM client (reads LLM_PROVIDER from config)
    try:
        llm_client = create_llm_client()
    except Exception as e:
        print(f"ERROR: Failed to initialize LLM client: {e}")
        sys.exit(1)

    is_local = LLM_PROVIDER.lower() == "ollama"
    print(f"Minimum blocks per entity: {args.min_blocks}")

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}")
            sys.exit(1)
        ingest_document(file_path, llm_client, args.min_blocks, is_local, use_checkpoint)
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
                ingest_document(file_path, llm_client, args.min_blocks, is_local, use_checkpoint)
            except Exception as e:
                print(f"\n  ERROR ingesting {file_path.name}: {e}")
                import traceback
                traceback.print_exc()

    print(f"\nIngestion complete!")


if __name__ == "__main__":
    main()
