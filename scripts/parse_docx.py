"""
Parses .docx files into ContentBlocks, preserving verbatim text.
Also extracts embedded images.
"""
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT


@dataclass
class ContentBlock:
    doc_filename: str
    heading_path: list
    paragraph_index: int
    text: str
    style: str
    block_type: str  # "paragraph" | "table_cell" | "heading"
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


def parse_docx(file_path: Path) -> tuple[list[ContentBlock], list[ExtractedImage]]:
    """
    Parse a .docx file into ContentBlocks and extracted images.
    All text is extracted verbatim -- no transformation.
    """
    doc = Document(str(file_path))

    blocks: list[ContentBlock] = []
    images: list[ExtractedImage] = []
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
