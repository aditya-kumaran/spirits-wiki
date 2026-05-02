"""
Parses .docx files into ContentBlocks, preserving verbatim text.
Also extracts embedded images.
Supports gallery document format (H1 = entity, images + captions).
"""
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from docx import Document
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT


@dataclass
class ContentBlock:
    doc_filename: str
    heading_path: list
    paragraph_index: int
    text: str
    style: str
    block_type: str  # "paragraph" | "table_cell" | "heading"
    indent_level: int = 0  # 0 = top-level, 1+ = nested bullets/sub-items
    parent_context: str = ""  # Text of the parent item (for sub-bullets)
    content_hash: str = field(init=False)

    def __post_init__(self):
        self.content_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass
class ExtractedImage:
    doc_filename: str
    image_index: int
    filename: str
    content_type: str
    image_bytes: bytes
    heading_context: list  # The heading path where the image was found near
    content_hash: str = field(init=False)

    def __post_init__(self):
        self.content_hash = hashlib.sha256(self.image_bytes).hexdigest()


def _get_indent_level(para) -> int:
    """
    Determine the indentation/nesting level of a paragraph.
    Checks list level (numPr/ilvl), style name ('List Bullet 2', etc.),
    and raw indentation (ind/@left).
    """
    # Check for explicit list level via numbering properties
    pPr = para._element.find(qn('w:pPr'))
    if pPr is not None:
        numPr = pPr.find(qn('w:numPr'))
        if numPr is not None:
            ilvl = numPr.find(qn('w:ilvl'))
            if ilvl is not None:
                try:
                    return int(ilvl.get(qn('w:val'), '0'))
                except (ValueError, TypeError):
                    pass

        # Check raw indentation
        ind = pPr.find(qn('w:ind'))
        if ind is not None:
            left = ind.get(qn('w:left'), '0')
            try:
                # Indentation in twips; ~720 twips per indent level
                twips = int(left)
                if twips > 0:
                    return min(twips // 720, 5)  # Cap at 5 levels
            except (ValueError, TypeError):
                pass

    # Check style name for list level hints
    style_name = para.style.name if para.style else ""
    if "List" in style_name or "Bullet" in style_name:
        # e.g., "List Bullet 2" -> level 1, "List Bullet 3" -> level 2
        for part in style_name.split():
            try:
                level_num = int(part)
                return max(0, level_num - 1)
            except ValueError:
                continue
        return 0  # Base list level

    return 0


def parse_docx(file_path: Path) -> tuple[list[ContentBlock], list[ExtractedImage]]:
    """
    Parse a .docx file into ContentBlocks and extracted images.
    All text is extracted verbatim -- no transformation.
    Captures indentation level and parent context for pronoun resolution.
    """
    doc = Document(str(file_path))

    blocks: list[ContentBlock] = []
    images: list[ExtractedImage] = []
    current_heading_path: list[str] = []
    heading_levels: list[int] = []

    # Track recent top-level text for parent context
    # Stack: [(indent_level, text)] — most recent items at each level
    context_stack: list[tuple[int, str]] = []

    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name if para.style else "Normal"
        indent_level = _get_indent_level(para)

        # Track heading hierarchy
        if style_name.startswith("Heading"):
            try:
                level = int(style_name.split()[-1])
            except (ValueError, IndexError):
                level = 1

            while heading_levels and heading_levels[-1] >= level:
                heading_levels.pop()
                current_heading_path.pop()

            current_heading_path.append(text)
            heading_levels.append(level)
            # Reset context stack on new heading
            context_stack = []

            blocks.append(ContentBlock(
                doc_filename=file_path.name,
                heading_path=list(current_heading_path),
                paragraph_index=i,
                text=text,
                style=style_name,
                block_type="heading",
                indent_level=0,
                parent_context="",
            ))
        else:
            # Determine parent context from context stack
            parent_context = ""
            if indent_level > 0 and context_stack:
                # Find the most recent item at a lower indent level
                for ctx_level, ctx_text in reversed(context_stack):
                    if ctx_level < indent_level:
                        parent_context = ctx_text
                        break

            # Update context stack: remove items at same or deeper level
            context_stack = [
                (lvl, txt) for lvl, txt in context_stack if lvl < indent_level
            ]
            context_stack.append((indent_level, text))

            blocks.append(ContentBlock(
                doc_filename=file_path.name,
                heading_path=list(current_heading_path),
                paragraph_index=i,
                text=text,
                style=style_name,
                block_type="paragraph",
                indent_level=indent_level,
                parent_context=parent_context,
            ))

    # Extract table content
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

    # Extract embedded images
    image_idx = 0
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            try:
                image_part = rel.target_part
                img_bytes = image_part.blob
                content_type = image_part.content_type or "image/png"

                # Determine file extension
                ext_map = {
                    "image/png": ".png",
                    "image/jpeg": ".jpg",
                    "image/gif": ".gif",
                    "image/bmp": ".bmp",
                    "image/webp": ".webp",
                    "image/tiff": ".tiff",
                }
                ext = ext_map.get(content_type, ".png")
                img_filename = f"{file_path.stem}_img_{image_idx}{ext}"

                images.append(ExtractedImage(
                    doc_filename=file_path.name,
                    image_index=image_idx,
                    filename=img_filename,
                    content_type=content_type,
                    image_bytes=img_bytes,
                    heading_context=list(current_heading_path),
                ))
                image_idx += 1
            except Exception as e:
                print(f"  Warning: Failed to extract image {image_idx}: {e}")

    return blocks, images


@dataclass
class GalleryImage:
    """An image extracted from a gallery-format document, paired with its entity and caption."""
    entity_name: str
    image_index: int
    filename: str
    content_type: str
    image_bytes: bytes
    caption: Optional[str]
    doc_filename: str
    content_hash: str = field(init=False)

    def __post_init__(self):
        self.content_hash = hashlib.sha256(self.image_bytes).hexdigest()


def _extract_images_from_paragraph(para, doc_part) -> list[tuple[bytes, str]]:
    """
    Extract inline image bytes from a paragraph's XML.
    Returns list of (image_bytes, content_type) tuples.
    """
    images = []
    # Find all <a:blip> elements which reference embedded images
    for blip in para._element.iter(qn('a:blip')):
        r_embed = blip.get(qn('r:embed'))
        if not r_embed:
            continue
        try:
            rel = doc_part.rels[r_embed]
            image_part = rel.target_part
            images.append((image_part.blob, image_part.content_type or "image/png"))
        except (KeyError, Exception):
            continue
    return images


def parse_gallery_docx(file_path: Path) -> list[GalleryImage]:
    """
    Parse a gallery-format .docx file.

    Expected structure (repeating for each character):
        Heading 1: Character Name
        [image paragraph(s)]
        Plain text: caption(s) for the images above

    Returns a flat list of GalleryImage objects, each linked to an entity name.
    """
    doc = Document(str(file_path))
    gallery_images: list[GalleryImage] = []

    current_entity: Optional[str] = None
    # Buffer of images found under the current entity that don't yet have captions
    pending_images: list[tuple[bytes, str]] = []  # (image_bytes, content_type)
    global_img_idx = 0

    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/webp": ".webp",
        "image/tiff": ".tiff",
    }

    def flush_pending(caption: Optional[str] = None):
        """Flush pending images, assigning the given caption (or None) to each."""
        nonlocal global_img_idx, pending_images
        for img_bytes, ctype in pending_images:
            ext = ext_map.get(ctype, ".png")
            fname = f"{file_path.stem}_gallery_{global_img_idx}{ext}"
            gallery_images.append(GalleryImage(
                entity_name=current_entity or "Unknown",
                image_index=global_img_idx,
                filename=fname,
                content_type=ctype,
                image_bytes=img_bytes,
                caption=caption,
                doc_filename=file_path.name,
            ))
            global_img_idx += 1
        pending_images = []

    for para in doc.paragraphs:
        style_name = para.style.name if para.style else "Normal"
        text = para.text.strip()

        # Detect Heading 1 or Heading 2 → new entity
        if style_name in ("Heading 1", "Heading 2") and text:
            # Flush any remaining images from previous entity with no caption
            if pending_images and current_entity:
                flush_pending(None)
            current_entity = text
            continue

        if not current_entity:
            continue

        # Check if this paragraph contains images
        para_images = _extract_images_from_paragraph(para, doc.part)

        if para_images:
            # If we had pending images waiting for a caption, flush them without one
            # (because we hit another image paragraph instead of a caption)
            if pending_images:
                flush_pending(None)
            pending_images = para_images
            continue

        # Plain text paragraph — treat as caption for pending images
        if text and pending_images:
            flush_pending(text)
        elif text:
            # Text but no pending images — could be a multi-line caption scenario
            # or text between image groups. Skip it.
            pass

    # Flush any remaining images at end of document
    if pending_images and current_entity:
        flush_pending(None)

    return gallery_images
