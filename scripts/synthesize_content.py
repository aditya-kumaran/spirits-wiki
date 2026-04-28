"""
Synthesizes wiki page content from source blocks using the LLM.
The LLM writes coherent wiki prose, but every claim MUST have a citation
pointing back to the exact source text from the .docx files.

Citations use markdown footnote format:
  Some claim about the entity. [^1]

  ## References
  [^1]: **Document.docx**, §Heading > Subheading — "exact source quote..."
"""
import json
import time
from typing import Optional

from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL


SYNTHESIS_PROMPT = """You are writing a wiki article about "{entity_name}" (type: {entity_type}) for a fictional world encyclopedia.

You MUST write coherent, well-organized wiki prose. However, every factual claim must be supported by a citation from the provided source material. Use markdown footnote syntax: [^1], [^2], etc.

RULES:
1. Write in an encyclopedic, third-person style.
2. Every factual statement MUST have at least one footnote citation [^N] referencing the source material below.
3. Do NOT invent any facts not present in the sources. If something is unclear, say so.
4. Organize the content with markdown ## headings. Use whichever sections are appropriate for the content (e.g., Overview, History, Relationships, Abilities, Culture, etc.). Skip sections that have no source material.
5. Use [[Entity Name]] syntax to link to other wiki entities mentioned in the text (for cross-linking).
6. At the end, include a ## References section listing every footnote with the source document, heading path, and a SHORT direct quote (the key phrase, not the full paragraph).

SOURCE MATERIAL (each block has a reference ID):

{source_blocks}

Write the wiki article now. Remember: every claim needs a citation, and the References section must list all citations with source details and quotes."""


SYNTHESIS_PROMPT_LARGE = """You are writing a wiki article about "{entity_name}" (type: {entity_type}) for a fictional world encyclopedia.

You have {block_count} source blocks. Write a comprehensive wiki article synthesizing this information.

RULES:
1. Write in an encyclopedic, third-person style.
2. Every factual statement MUST have at least one footnote citation [^N].
3. Do NOT invent any facts. Only use information from the sources.
4. Use ## headings to organize (Overview, History, Relationships, etc.). Skip empty sections.
5. Use [[Entity Name]] to link to other entities.
6. End with ## References listing each footnote: source doc, heading, and a key quote.

SOURCE MATERIAL:

{source_blocks}

Write the wiki article now."""


def format_source_blocks(items: list) -> str:
    """Format source blocks with reference IDs for the LLM prompt."""
    lines = []
    for i, (block, classification) in enumerate(items, 1):
        heading_str = " > ".join(block.heading_path) if block.heading_path else "(no heading)"
        # Truncate very long blocks for the prompt
        text = block.text[:500] + "..." if len(block.text) > 500 else block.text
        lines.append(f"[REF-{i}] Source: {block.doc_filename}, §{heading_str}")
        lines.append(f"Text: \"{text}\"")
        lines.append("")
    return "\n".join(lines)


def synthesize_wiki_page(
    entity_name: str,
    entity_type: str,
    items: list,
    client: Optional[Groq] = None,
    model: str = GROQ_MODEL,
    max_retries: int = 3,
) -> str:
    """
    Use the LLM to write a wiki article from source blocks.
    Returns markdown with footnote citations.
    Falls back to structured verbatim layout if LLM fails.
    """
    if client is None:
        client = Groq(api_key=GROQ_API_KEY)

    source_text = format_source_blocks(items)

    # Choose prompt based on size
    if len(items) > 20:
        prompt = SYNTHESIS_PROMPT_LARGE.format(
            entity_name=entity_name,
            entity_type=entity_type,
            block_count=len(items),
            source_blocks=source_text,
        )
    else:
        prompt = SYNTHESIS_PROMPT.format(
            entity_name=entity_name,
            entity_type=entity_type,
            source_blocks=source_text,
        )

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
            )
            content = response.choices[0].message.content
            if content and len(content.strip()) > 50:
                return content.strip()

        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait_time = 2 ** attempt * 3
                print(f"    Rate limited during synthesis, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            print(f"  Synthesis failed for {entity_name}: {e}")

    # Fallback: structured verbatim content with citations
    return fallback_verbatim_content(entity_name, items)


def fallback_verbatim_content(entity_name: str, items: list) -> str:
    """
    Fallback when LLM synthesis fails.
    Returns structured verbatim content grouped by section with citations.
    """
    sections: dict = {}
    for block, classification in items:
        section = classification.section_type
        if section not in sections:
            sections[section] = []
        sections[section].append((block, classification))

    lines = [f"## Overview\n"]
    ref_lines = []
    ref_idx = 1

    for section_name, section_items in sections.items():
        if section_name != "overview":
            display_name = section_name.replace("_", " ").title()
            lines.append(f"\n## {display_name}\n")

        for block, classification in section_items:
            heading_str = " > ".join(block.heading_path) if block.heading_path else "N/A"
            lines.append(f"{block.text} [^{ref_idx}]\n")
            ref_lines.append(
                f"[^{ref_idx}]: **{block.doc_filename}**, §{heading_str} — "
                f"\"{block.text[:100]}{'...' if len(block.text) > 100 else ''}\""
            )
            ref_idx += 1

    lines.append("\n## References\n")
    lines.extend(ref_lines)

    return "\n".join(lines)
