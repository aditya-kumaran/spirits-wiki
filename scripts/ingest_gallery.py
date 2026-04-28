"""
Gallery document ingestion script.
Parses a gallery-format .docx file and links extracted images to existing wiki pages.

Gallery document format:
    Heading 1 or Heading 2: Character Name
    [image(s)]
    Plain text: caption for the image(s) above
    ... repeats for each character ...

Usage:
    python scripts/ingest_gallery.py --file path/to/gallery.docx
    python scripts/ingest_gallery.py --file path/to/gallery.docx --save-unmatched
"""
import argparse
import os
import sys
import uuid
from pathlib import Path

import psycopg2

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))

from config import DATABASE_URL
from parse_docx import parse_gallery_docx, GalleryImage


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


def save_image_locally(img: GalleryImage) -> str:
    """Save image to local uploads directory. Returns the URL path."""
    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "public", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    safe_filename = img.filename.replace(" ", "_")
    filepath = os.path.join(uploads_dir, safe_filename)
    with open(filepath, "wb") as f:
        f.write(img.image_bytes)

    return f"/uploads/{safe_filename}"


def ingest_gallery(file_path: Path, save_unmatched: bool = False):
    """
    Ingest a gallery document, linking images to existing wiki pages.
    """
    print(f"\n{'='*60}")
    print(f"Ingesting gallery: {file_path.name}")

    # Parse the gallery document
    print(f"  Parsing gallery document...")
    gallery_images = parse_gallery_docx(file_path)
    print(f"  Found {len(gallery_images)} images across gallery entries")

    # Group by entity name
    entities: dict[str, list[GalleryImage]] = {}
    for img in gallery_images:
        if img.entity_name not in entities:
            entities[img.entity_name] = []
        entities[img.entity_name].append(img)

    print(f"  Found {len(entities)} distinct characters in gallery")

    # Load existing pages from DB
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, slug, entity_name FROM pages")
        pages = cursor.fetchall()
    finally:
        conn.close()

    # Build lookup: slug -> (page_id, entity_name) and name_lower -> (page_id, slug)
    slug_to_page = {row[1]: (row[0], row[2]) for row in pages}
    name_to_page = {row[2].lower(): (row[0], row[1]) for row in pages}

    matched = 0
    unmatched = 0
    images_stored = 0
    unmatched_names = []

    for entity_name, images in entities.items():
        # Try to match by slug first, then by name
        slug = slugify(entity_name)
        page_id = None

        if slug in slug_to_page:
            page_id = slug_to_page[slug][0]
        elif entity_name.lower() in name_to_page:
            page_id = name_to_page[entity_name.lower()][0]
        else:
            # Try first-name matching: "John" matches "John Smith"
            # All character first names are unique, so this is safe
            entity_lower = entity_name.lower().strip()
            for pname_lower, (pid, _pslug) in name_to_page.items():
                # Check if page entity name starts with the gallery heading as a first name
                if pname_lower.startswith(entity_lower + " "):
                    page_id = pid
                    print(f"    First-name match: '{entity_name}' -> '{pname_lower}'")
                    break

            # Also try the reverse: gallery has full name, page has partial
            if not page_id:
                for pname_lower, (pid, _pslug) in name_to_page.items():
                    if entity_lower.startswith(pname_lower + " ") or pname_lower == entity_lower:
                        page_id = pid
                        break

        if not page_id:
            unmatched += 1
            unmatched_names.append(entity_name)
            if not save_unmatched:
                print(f"    No page found for: {entity_name} ({len(images)} images) — skipping")
                continue
            else:
                print(f"    No page found for: {entity_name} ({len(images)} images) — saving unlinked")
        else:
            matched += 1
            print(f"    Matched: {entity_name} -> page ({len(images)} images)")

        # Store each image
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            # Check if this is the first image for this page (make it primary)
            has_primary = False
            if page_id:
                cursor.execute(
                    "SELECT EXISTS(SELECT 1 FROM images WHERE page_id = %s AND is_primary = true)",
                    (page_id,)
                )
                has_primary = cursor.fetchone()[0]

            for i, img in enumerate(images):
                # Save image file locally
                url = save_image_locally(img)

                # First image for a page with no primary becomes the primary
                is_primary = (i == 0 and page_id is not None and not has_primary)

                # Check for duplicate by content hash
                cursor.execute(
                    "SELECT id FROM images WHERE url = %s OR (page_id = %s AND filename = %s)",
                    (url, page_id, img.filename)
                )
                if cursor.fetchone():
                    continue

                cursor.execute("""
                    INSERT INTO images
                    (id, page_id, filename, alt_text, caption, url, source_doc,
                     is_primary, origin, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'gallery-extracted', %s)
                """, (
                    str(uuid.uuid4()),
                    page_id,
                    img.filename,
                    img.entity_name,  # alt text = entity name
                    img.caption,
                    url,
                    img.doc_filename,
                    is_primary,
                    i,  # sort order = position in gallery
                ))
                images_stored += 1

                if is_primary:
                    has_primary = True

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"    ERROR storing images for {entity_name}: {e}")
        finally:
            conn.close()

    print(f"\n  Results:")
    print(f"    Characters matched:   {matched}")
    print(f"    Characters unmatched: {unmatched}")
    print(f"    Images stored:        {images_stored}")

    if unmatched_names:
        print(f"\n  Unmatched character names:")
        for name in sorted(unmatched_names):
            print(f"    - {name}")
        print(f"\n  Tip: These characters may not have wiki pages yet.")
        print(f"  Run the main ingestion first, then re-run this gallery ingestion.")


def main():
    parser = argparse.ArgumentParser(description="Ingest a gallery .docx file")
    parser.add_argument("--file", type=str, required=True,
                        help="Path to the gallery .docx file")
    parser.add_argument("--save-unmatched", action="store_true",
                        help="Save images even if no matching wiki page exists (stored without page link)")
    args = parser.parse_args()

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable is not set")
        sys.exit(1)

    # Verify DB connectivity
    try:
        conn = get_db_connection()
        conn.close()
        print("Database connection verified.")
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}")
        sys.exit(1)

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    ingest_gallery(file_path, args.save_unmatched)
    print(f"\nGallery ingestion complete!")


if __name__ == "__main__":
    main()
