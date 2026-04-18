"""
Vector index rebuild script.
Safe to re-run. Never touches relational data (pages, versions, source_chunks).
Only updates the embeddings table in pgvector.

Usage:
    python scripts/rebuild_index.py

To update the Q&A system after edits or new document ingestion, run this script.
This rebuilds the vector index without affecting any wiki content or edit history.

NOTE: This requires the pgvector extension enabled in your PostgreSQL database.
Run: CREATE EXTENSION IF NOT EXISTS vector;
And create the embeddings table (see prisma migrations or schema.sql).
"""
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import psycopg2

sys.path.insert(0, os.path.dirname(__file__))
from config import DATABASE_URL

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 32


def ensure_embeddings_table(cursor):
    """Create the embeddings table if it doesn't exist."""
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_type TEXT NOT NULL,
            source_id UUID NOT NULL,
            chunk_text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            embedding vector({EMBEDDING_DIM}) NOT NULL,
            metadata JSONB DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(source_type, source_id, content_hash)
        )
    """)
    # Create HNSW index for fast search
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_vector
        ON embeddings USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def rebuild_index():
    """Rebuild the entire vector index from current database state."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    # Lazy import so script fails fast if sentence-transformers not installed
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed.")
        print("Install: pip install sentence-transformers")
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    ensure_embeddings_table(cursor)
    conn.commit()

    model = SentenceTransformer(EMBEDDING_MODEL)

    build_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    cursor.execute("""
        INSERT INTO index_build_log (id, started_at, status, embedding_model)
        VALUES (%s, %s, 'running', %s)
    """, (build_id, started_at, EMBEDDING_MODEL))
    conn.commit()

    try:
        chunks_indexed = 0
        pages_indexed = 0

        # Step 1: Embed source chunks
        cursor.execute("""
            SELECT id, text, doc_filename, heading_path, entity_name, section_type
            FROM source_chunks
            WHERE text IS NOT NULL AND length(text) > 10
        """)
        source_chunks = cursor.fetchall()
        print(f"Embedding {len(source_chunks)} source chunks...")

        for i in range(0, len(source_chunks), BATCH_SIZE):
            batch = source_chunks[i:i + BATCH_SIZE]
            texts = [row[1][:1000] for row in batch]  # Truncate long texts
            embeddings = model.encode(texts, show_progress_bar=False)

            for row, embedding in zip(batch, embeddings):
                chunk_id, text, doc_filename, heading_path, entity_name, section_type = row
                content_hash = hashlib.sha256(text[:1000].encode()).hexdigest()
                metadata = json.dumps({
                    "doc_filename": doc_filename,
                    "heading_path": heading_path,
                    "entity_name": entity_name,
                    "section_type": section_type,
                })

                cursor.execute("""
                    INSERT INTO embeddings
                    (id, source_type, source_id, chunk_text, content_hash, embedding, metadata)
                    VALUES (%s, 'source_chunk', %s, %s, %s, %s::vector, %s::jsonb)
                    ON CONFLICT (source_type, source_id, content_hash)
                    DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        chunk_text = EXCLUDED.chunk_text,
                        metadata = EXCLUDED.metadata,
                        created_at = NOW()
                """, (str(uuid.uuid4()), str(chunk_id), text[:1000], content_hash,
                      embedding.tolist(), metadata))
                chunks_indexed += 1

            conn.commit()
            print(f"  {min(i + BATCH_SIZE, len(source_chunks))}/{len(source_chunks)} chunks embedded")

        # Step 2: Embed wiki page sections
        cursor.execute("""
            SELECT id, slug, entity_name, content_markdown
            FROM pages
            WHERE content_markdown IS NOT NULL AND length(content_markdown) > 10
        """)
        pages = cursor.fetchall()
        print(f"\nEmbedding {len(pages)} wiki pages...")

        for page_id, slug, entity_name, content_md in pages:
            sections = split_into_sections(content_md)
            for section_title, section_text in sections:
                if len(section_text.strip()) < 10:
                    continue
                embed_text = f"{entity_name} - {section_title}: {section_text[:800]}"
                content_hash = hashlib.sha256(embed_text.encode()).hexdigest()
                embedding = model.encode(embed_text)
                metadata = json.dumps({
                    "page_slug": slug,
                    "entity_name": entity_name,
                    "section_title": section_title,
                })

                cursor.execute("""
                    INSERT INTO embeddings
                    (id, source_type, source_id, chunk_text, content_hash, embedding, metadata)
                    VALUES (%s, 'wiki_page_section', %s, %s, %s, %s::vector, %s::jsonb)
                    ON CONFLICT (source_type, source_id, content_hash)
                    DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        chunk_text = EXCLUDED.chunk_text,
                        metadata = EXCLUDED.metadata,
                        created_at = NOW()
                """, (str(uuid.uuid4()), str(page_id), embed_text, content_hash,
                      embedding.tolist(), metadata))

            pages_indexed += 1
            conn.commit()

        # Step 3: Log completion
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

        print(f"\nIndex rebuild complete:")
        print(f"  Chunks indexed: {chunks_indexed}")
        print(f"  Pages indexed:  {pages_indexed}")
        print(f"  Duration:       {duration:.1f}s")

    except Exception as e:
        cursor.execute("""
            UPDATE index_build_log
            SET status = 'failed', error_message = %s, completed_at = NOW()
            WHERE id = %s
        """, (str(e), build_id))
        conn.commit()
        raise
    finally:
        cursor.close()
        conn.close()


def split_into_sections(markdown: str) -> list:
    """Split markdown into (section_title, section_text) pairs."""
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
