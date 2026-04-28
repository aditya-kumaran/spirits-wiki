"""
Synthesizes wiki page content from source blocks using the LLM.
The LLM writes coherent wiki prose, but every claim MUST have a citation
pointing back to the exact source text from the .docx files.

Supports both Groq (cloud) and Ollama (local) via LLMClient.

Citations use markdown footnote format:
  Some claim about the entity. [^1]

  ## References
  [^1]: **Document.docx**, §Heading > Subheading — "exact source quote..."
"""
import json
import re
import time
from typing import Optional

from llm_client import LLMClient


# --- Character-specific prompt ---
CHARACTER_SYNTHESIS_PROMPT = """You are writing a wiki article about the character "{entity_name}".

You MUST write coherent, well-organized wiki prose. Every factual claim must be supported by a citation from the source material. Use markdown footnote syntax: [^1], [^2], etc.

IMPORTANT STRUCTURAL RULES FOR CHARACTERS:

1. Start with a metadata block in EXACTLY this format (fill in values from source material, leave blank if unknown):
<!--META
spirit: 
aura: 
eyes: 
hair: 
build: 
style: 
inspiration: 
age: 
power_set: 
home_system: 
language: 
-->

2. After the metadata block, write the article with these sections:
   - ## Overview — Brief description of who this character is
   - ## Relationships — Notable relationships with other characters. Include personality traits that relate to how this character interacts with others. If source material references time periods, ages, parts, or eras, organize with ### subheadings for each era, e.g.:
     ### Part One
     ### Part Two
     ### Golden Age (2000-3000)
     Personality traits (e.g., "is jealous of brother", "very polite and coy") should be woven into the relevant relationship or era subsection rather than listed separately.
   - ## Abilities — Powers, skills, or notable abilities (if any)
   - ## Plot — THIS IS CRITICAL: Organize plot points by era/age/part. Use ### subheadings for each era, e.g.:
     ### Part One
     ### Part Two
     ### Golden Age (2000-3000)
     If source material references time periods, ages, parts, or eras, use those as subheadings. If no era info is available, just write the plot chronologically.
   - Do NOT create a separate "Traits" section. Personality traits belong inside Relationships (organized by era if applicable).
   - Skip sections that have no source material.

3. Use [[Entity Name]] syntax to link to other wiki entities.
4. Do NOT introduce the character by saying they are "a character in" or "from" any fictional world.
5. Every factual statement MUST have a footnote citation [^N].
6. End with ## References listing each footnote on its own line: [^N]: **Source.docx**, §Heading — "quote"

SOURCE MATERIAL (each block has a reference ID):

{source_blocks}

Write the wiki article now. Start with the <!--META block, then the article content."""


# --- Location-specific prompt ---
LOCATION_SYNTHESIS_PROMPT = """You are writing a wiki article about the location "{entity_name}".

You MUST write coherent, well-organized wiki prose. Every factual claim must be supported by a citation. Use markdown footnote syntax: [^1], [^2], etc.

IMPORTANT STRUCTURAL RULES FOR LOCATIONS:

1. Organize the article with these sections:
   - ## Overview — Brief description of this location
   - ## Geography — Physical features and layout
   - ## Culture — Cultural significance and customs
   - ## History — THIS IS CRITICAL: Organize history by era/age/part. Use ### subheadings for each era, e.g.:
     ### Golden Age (2000-3000)
     ### Age of Freedom (3000-)
     ### Part One
     If source material references time periods, ages, parts, or eras, use those as subheadings. If no era info is available, just write chronologically.
   - ## Notable Residents — Important figures associated with this location
   - Skip sections that have no source material.

2. Use [[Entity Name]] syntax to link to other wiki entities.
3. Do NOT introduce the location by saying it is "a location in" or "from" any fictional world.
4. Every factual statement MUST have a footnote citation [^N].
5. End with ## References listing each footnote on its own line: [^N]: **Source.docx**, §Heading — "quote"

SOURCE MATERIAL (each block has a reference ID):

{source_blocks}

Write the wiki article now."""


# --- Generic prompt (non-character, non-location) ---
SYNTHESIS_PROMPT = """You are writing a wiki article about "{entity_name}" (type: {entity_type}).

You MUST write coherent, well-organized wiki prose. However, every factual claim must be supported by a citation from the provided source material. Use markdown footnote syntax: [^1], [^2], etc.

RULES:
1. Write in an encyclopedic, third-person style.
2. Every factual statement MUST have at least one footnote citation [^N] referencing the source material below.
3. Do NOT invent any facts not present in the sources. If something is unclear, say so.
4. Do NOT introduce the entity by saying they are "a character in" or "from" any fictional world. Just describe them directly — start with what they are or what they do.
5. Organize the content with markdown ## headings. Use whichever sections are appropriate for the content (e.g., Overview, History, Relationships, Abilities, Culture, etc.). Skip sections that have no source material.
6. Where the source material references time periods, ages, parts, or eras (e.g., "Golden Age", "Part One", "Age of Freedom"), organize relevant sections with ### subheadings for each era.
7. Use [[Entity Name]] syntax to link to other wiki entities mentioned in the text (for cross-linking).
8. At the end, include a ## References section listing every footnote with the source document, heading path, and a SHORT direct quote (the key phrase, not the full paragraph). Each reference MUST be on its own line in the format: [^N]: **Source.docx**, §Heading — "quote"

SOURCE MATERIAL (each block has a reference ID):

{source_blocks}

Write the wiki article now. Remember: every claim needs a citation, and the References section must list all citations with source details and quotes."""


SYNTHESIS_PROMPT_LARGE = """You are writing a wiki article about "{entity_name}" (type: {entity_type}).

You have {block_count} source blocks. Write a comprehensive wiki article synthesizing this information.

RULES:
1. Write in an encyclopedic, third-person style.
2. Every factual statement MUST have at least one footnote citation [^N].
3. Do NOT invent any facts. Only use information from the sources.
4. Do NOT introduce the entity by saying they are "a character in" or "from" any fictional world. Just describe them directly.
5. Use ## headings to organize. For characters, use: Overview, Relationships (with ### era subheadings — weave personality traits into relationships/era subsections, do NOT create a separate Traits section), Abilities, Plot (with ### era subheadings). For locations, use: Overview, Geography, Culture, History (with ### era subheadings). Skip empty sections.
6. Where source material references time periods, ages, or parts, organize Plot/History with ### subheadings for each era (e.g., ### Part One, ### Golden Age).
7. Use [[Entity Name]] to link to other entities.
8. End with ## References listing each footnote on its own line: [^N]: **Source.docx**, §Heading — "quote"

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


def parse_character_metadata(content: str) -> tuple[dict, str]:
    """
    Extract <!--META ... --> block from LLM output.
    Returns (metadata_dict, content_without_meta).
    """
    meta_pattern = r'<!--\s*META\s*\n(.*?)-->'
    match = re.search(meta_pattern, content, re.DOTALL)

    if not match:
        return {}, content

    meta_text = match.group(1)
    metadata = {}

    appearance = {}
    for line in meta_text.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if not value:
                continue

            # Map to structured fields
            if key == "spirit":
                metadata["spirit"] = value
            elif key == "aura":
                metadata["aura"] = value
            elif key == "eyes":
                appearance["eyes"] = value
            elif key == "hair":
                appearance["hair"] = value
            elif key == "build":
                appearance["build"] = value
            elif key == "style":
                appearance["style"] = value
            elif key == "inspiration":
                metadata["inspiration"] = value
            elif key == "age":
                metadata["age"] = value
            elif key in ("power_set", "powerset"):
                metadata["powerSet"] = value
            elif key in ("home_system", "homesystem"):
                metadata["homeSystem"] = value
            elif key == "language":
                metadata["language"] = value

    if appearance:
        metadata["appearance"] = appearance

    # Remove the META block from content
    clean_content = content[:match.start()] + content[match.end():]
    clean_content = clean_content.strip()

    return metadata, clean_content


def synthesize_wiki_page(
    entity_name: str,
    entity_type: str,
    items: list,
    client: LLMClient,
    max_retries: int = 3,
) -> tuple[str, dict]:
    """
    Use the LLM to write a wiki article from source blocks.
    Returns (markdown_with_citations, metadata_dict).
    Falls back to structured verbatim layout if LLM fails.
    """
    source_text = format_source_blocks(items)
    metadata = {}

    # Choose prompt based on entity type and size
    if entity_type == "character":
        prompt = CHARACTER_SYNTHESIS_PROMPT.format(
            entity_name=entity_name,
            source_blocks=source_text,
        )
    elif entity_type == "location":
        prompt = LOCATION_SYNTHESIS_PROMPT.format(
            entity_name=entity_name,
            source_blocks=source_text,
        )
    elif len(items) > 20:
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
            content = client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
                json_mode=False,
            )
            if content and len(content.strip()) > 50:
                content = content.strip()

                # Extract character metadata if present
                if entity_type == "character":
                    metadata, content = parse_character_metadata(content)

                return content, metadata

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
    return fallback_verbatim_content(entity_name, items), {}


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
