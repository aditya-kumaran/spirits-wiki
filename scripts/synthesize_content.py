"""
Synthesizes wiki page content from source blocks using the LLM.
The LLM outputs STRUCTURED JSON with predefined section keys per entity type.
The JSON is then deterministically converted to wiki markdown.

This approach prevents the LLM from injecting preamble text, generic intros,
or straying from the template — the schema enforces the exact structure.

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


# ──────────────────────────────────────────────────────────
# JSON SCHEMA PROMPTS — one per entity type
# ──────────────────────────────────────────────────────────

CHARACTER_JSON_PROMPT = """You are a wiki content generator. Given source material about the character "{entity_name}", produce a JSON object with EXACTLY the keys shown below. Do NOT output anything except valid JSON — no preamble, no explanation, no markdown fences.

REQUIRED JSON SCHEMA:
{{
  "metadata": {{
    "spirit": "",
    "aura": "",
    "eyes": "",
    "hair": "",
    "build": "",
    "style": "",
    "inspiration": "",
    "age": "",
    "power_set": "",
    "home_system": "",
    "language": ""
  }},
  "overview": "One or two paragraphs describing who this character is. Every claim needs a citation like [^1].",
  "relationships": {{
    "_default": "Content for relationships not tied to a specific era. [^N]",
    "Part One": "Relationships and personality traits during Part One. [^N]",
    "Part Two": "Relationships and personality traits during Part Two. [^N]"
  }},
  "abilities": "Description of powers, skills, or notable abilities. [^N]",
  "plot": {{
    "_default": "Plot points not tied to a specific era. [^N]",
    "Part One": "Plot events during Part One. [^N]",
    "Part Two": "Plot events during Part Two. [^N]"
  }},
  "references": [
    "[^1]: **SourceFile.docx**, §Heading > Subheading — \\"exact short quote\\""
  ]
}}

RULES:
- Fill "metadata" fields by COPYING EXACTLY from the source material — do NOT rewrite, summarize, or paraphrase any metadata value. If the source says "Loki x Scar (Lion King)" for inspiration, write exactly that.
- "overview": Write 1-2 paragraphs. Do NOT say "X is a character in the fictional world of Y" — just describe who they are directly.
- "relationships": Object with era subheading keys. Use "_default" for content not tied to any era. Weave personality traits into relationship descriptions. Use [[Entity Name]] for wiki links.
- "abilities": String. Set to "" if no abilities info exists.
- "plot": Object with era subheading keys. Use "_default" for content not tied to any era. Organize chronologically within each era.
- REFERENCES ARE CRITICAL. Each reference MUST include the actual source filename, heading path, AND a direct quote from the source material. Do NOT just write "[REF-1]" — you must expand each [REF-N] tag into the full citation with the real filename and a real quote. Example: [^1]: **Spirits_Faces.docx**, §Characters > Devin — "possesses the Menora Cystium"
- Every factual claim in overview/relationships/abilities/plot MUST have a [^N] citation.
- Use [[Entity Name]] syntax to link to other entities.
- Era keys in relationships and plot should match what the source material mentions (e.g., "Part One", "Golden Age (2000-3000)", "Age of Freedom"). Only include eras that have source material.
- Omit sections (set to "" or {{}}) if no source material exists for them.

SOURCE MATERIAL:

{source_blocks}

Respond with ONLY the JSON object. No other text."""


LOCATION_JSON_PROMPT = """You are a wiki content generator. Given source material about the location "{entity_name}", produce a JSON object with EXACTLY the keys shown below. Do NOT output anything except valid JSON — no preamble, no explanation, no markdown fences.

REQUIRED JSON SCHEMA:
{{
  "overview": "One or two paragraphs describing this location. Every claim needs a citation like [^1].",
  "geography": "Physical features and layout. [^N]",
  "culture": "Cultural significance and customs. [^N]",
  "history": {{
    "_default": "History not tied to a specific era. [^N]",
    "Golden Age (2000-3000)": "Events during this era. [^N]"
  }},
  "notable_residents": "Important figures associated with this location. [^N]",
  "references": [
    "[^1]: **SourceFile.docx**, §Heading > Subheading — \\"exact short quote\\""
  ]
}}

RULES:
- "overview": 1-2 paragraphs. Do NOT say "X is a location in the fictional world of Y."
- "geography", "culture", "notable_residents": Strings. Set to "" if no info.
- "history": Object with era subheading keys. Use "_default" for non-era content.
- REFERENCES ARE CRITICAL. Each reference MUST include the actual source filename, heading path, AND a direct quote from the source material. Do NOT just write "[REF-1]" — expand each into a full citation. Example: [^1]: **Nationalities.docx**, §Locations > Dubai — "a sprawling desert city"
- Every factual claim MUST have a [^N] citation.
- Use [[Entity Name]] to link to other entities.
- Only include eras/sections that have source material.

SOURCE MATERIAL:

{source_blocks}

Respond with ONLY the JSON object. No other text."""


GENERIC_JSON_PROMPT = """You are a wiki content generator. Given source material about "{entity_name}" (type: {entity_type}), produce a JSON object with EXACTLY the keys shown below. Do NOT output anything except valid JSON — no preamble, no explanation, no markdown fences.

REQUIRED JSON SCHEMA:
{{
  "overview": "One or two paragraphs describing this entity. Every claim needs a citation like [^1].",
  "sections": {{
    "Section Name": "Content for this section. [^N]"
  }},
  "references": [
    "[^1]: **SourceFile.docx**, §Heading > Subheading — \\"exact short quote\\""
  ]
}}

RULES:
- "overview": 1-2 paragraphs. Do NOT say "X is a Y in the fictional world of Z."
- "sections": Object with section name keys. Choose appropriate section names for the entity type (e.g., History, Culture, Significance, Members, etc.). Only include sections with source material.
- REFERENCES ARE CRITICAL. Each reference MUST include the actual source filename, heading path, AND a direct quote from the source material. Do NOT just write "[REF-1]" — expand each into a full citation. Example: [^1]: **Philosophies.docx**, §Concepts > Magic — "the fundamental force"
- Every factual claim MUST have a [^N] citation.
- Use [[Entity Name]] to link to other entities.

SOURCE MATERIAL:

{source_blocks}

Respond with ONLY the JSON object. No other text."""


# ──────────────────────────────────────────────────────────
# JSON -> Markdown converters
# ──────────────────────────────────────────────────────────

def _render_era_section(section_name: str, data) -> str:
    """Render a section that can be either a string or an object with era keys."""
    lines = []
    if isinstance(data, dict):
        # Has era subsections
        default_content = data.get("_default", "").strip()
        if default_content:
            lines.append(f"## {section_name}\n")
            lines.append(default_content)
            lines.append("")

        has_eras = False
        for key, val in data.items():
            if key == "_default" or not val or not val.strip():
                continue
            if not has_eras:
                if not default_content:
                    lines.append(f"## {section_name}\n")
                has_eras = True
            lines.append(f"### {key}\n")
            lines.append(val.strip())
            lines.append("")

        if not default_content and not has_eras:
            return ""
    elif isinstance(data, str) and data.strip():
        lines.append(f"## {section_name}\n")
        lines.append(data.strip())
        lines.append("")
    else:
        return ""

    return "\n".join(lines)


def character_json_to_markdown(data: dict) -> tuple[str, dict]:
    """Convert character JSON to markdown + metadata dict."""
    metadata = {}
    raw_meta = data.get("metadata", {})
    if isinstance(raw_meta, dict):
        appearance = {}
        for key, val in raw_meta.items():
            if not val or not str(val).strip():
                continue
            val = str(val).strip()
            if key == "spirit":
                metadata["spirit"] = val
            elif key == "aura":
                metadata["aura"] = val
            elif key == "eyes":
                appearance["eyes"] = val
            elif key == "hair":
                appearance["hair"] = val
            elif key == "build":
                appearance["build"] = val
            elif key == "style":
                appearance["style"] = val
            elif key == "inspiration":
                metadata["inspiration"] = val
            elif key == "age":
                metadata["age"] = val
            elif key in ("power_set", "powerset"):
                metadata["powerSet"] = val
            elif key in ("home_system", "homesystem"):
                metadata["homeSystem"] = val
            elif key == "language":
                metadata["language"] = val
        if appearance:
            metadata["appearance"] = appearance

    parts = []

    # Overview
    overview = data.get("overview", "").strip()
    if overview:
        parts.append(f"## Overview\n\n{overview}")

    # Relationships (era-based)
    rel = _render_era_section("Relationships", data.get("relationships", ""))
    if rel:
        parts.append(rel)

    # Abilities
    abilities = data.get("abilities", "").strip()
    if abilities:
        parts.append(f"## Abilities\n\n{abilities}")

    # Plot (era-based)
    plot = _render_era_section("Plot", data.get("plot", ""))
    if plot:
        parts.append(plot)

    # References
    refs = data.get("references", [])
    if refs and isinstance(refs, list):
        parts.append("## References\n")
        for ref in refs:
            parts.append(str(ref))

    md = "\n\n".join(parts)
    return md, metadata


def location_json_to_markdown(data: dict) -> tuple[str, dict]:
    """Convert location JSON to markdown."""
    parts = []

    overview = data.get("overview", "").strip()
    if overview:
        parts.append(f"## Overview\n\n{overview}")

    geography = data.get("geography", "").strip()
    if geography:
        parts.append(f"## Geography\n\n{geography}")

    culture = data.get("culture", "").strip()
    if culture:
        parts.append(f"## Culture\n\n{culture}")

    history = _render_era_section("History", data.get("history", ""))
    if history:
        parts.append(history)

    residents = data.get("notable_residents", "").strip()
    if residents:
        parts.append(f"## Notable Residents\n\n{residents}")

    refs = data.get("references", [])
    if refs and isinstance(refs, list):
        parts.append("## References\n")
        for ref in refs:
            parts.append(str(ref))

    md = "\n\n".join(parts)
    return md, {}


def generic_json_to_markdown(data: dict) -> tuple[str, dict]:
    """Convert generic entity JSON to markdown."""
    parts = []

    overview = data.get("overview", "").strip()
    if overview:
        parts.append(f"## Overview\n\n{overview}")

    sections = data.get("sections", {})
    if isinstance(sections, dict):
        for name, content in sections.items():
            if content and str(content).strip():
                parts.append(f"## {name}\n\n{str(content).strip()}")

    refs = data.get("references", [])
    if refs and isinstance(refs, list):
        parts.append("## References\n")
        for ref in refs:
            parts.append(str(ref))

    md = "\n\n".join(parts)
    return md, {}


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

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


def build_ref_lookup(items: list) -> dict[int, str]:
    """Build a lookup from REF-N index to a properly formatted citation string."""
    lookup = {}
    for i, (block, classification) in enumerate(items, 1):
        heading_str = " > ".join(block.heading_path) if block.heading_path else "(no heading)"
        quote = block.text[:120].replace('"', "'")
        if len(block.text) > 120:
            quote += "..."
        lookup[i] = f"**{block.doc_filename}**, §{heading_str} — \"{quote}\""
    return lookup


def fix_references(md: str, ref_lookup: dict[int, str]) -> str:
    """
    Post-process markdown to fix broken references.
    - Replace bare [REF-N] in reference lines with actual source citations
    - Replace references that are just "[REF-N]" with expanded text
    - Ensure every [^N] reference line has actual source info
    """
    lines = md.split("\n")
    result = []
    in_references = False

    for line in lines:
        if re.match(r'^##\s*References?\s*$', line, re.IGNORECASE):
            in_references = True
            result.append(line)
            continue

        if in_references:
            # Fix reference lines that just contain [REF-N] placeholders
            # Pattern: [^1]: [REF-1] or [^1]: **[REF-1]** etc.
            ref_line_match = re.match(r'^\[\^(\d+)\]:\s*(.*)', line)
            if ref_line_match:
                ref_num = int(ref_line_match.group(1))
                ref_text = ref_line_match.group(2).strip()

                # Check if the reference text is just REF-N placeholders
                if re.match(r'^\[?REF-\d+\]?$', ref_text) or not ref_text or ref_text.startswith("[REF-"):
                    # Extract the REF number from the text if present
                    ref_id_match = re.search(r'REF-(\d+)', ref_text)
                    ref_id = int(ref_id_match.group(1)) if ref_id_match else ref_num
                    if ref_id in ref_lookup:
                        result.append(f"[^{ref_num}]: {ref_lookup[ref_id]}")
                        continue

                # Also fix lines where REF-N appears anywhere in the citation
                fixed_text = ref_text
                for match in re.finditer(r'\[?REF-(\d+)\]?', ref_text):
                    ref_id = int(match.group(1))
                    if ref_id in ref_lookup:
                        fixed_text = fixed_text.replace(match.group(0), ref_lookup[ref_id])
                if fixed_text != ref_text:
                    result.append(f"[^{ref_num}]: {fixed_text}")
                    continue

            # Fix standalone lines that are just "N. [REF-N]"
            bare_match = re.match(r'^(\d+)\.\s*\[?REF-(\d+)\]?\s*$', line)
            if bare_match:
                num = bare_match.group(1)
                ref_id = int(bare_match.group(2))
                if ref_id in ref_lookup:
                    result.append(f"[^{num}]: {ref_lookup[ref_id]}")
                    continue

        result.append(line)

    return "\n".join(result)


def extract_json_from_response(response: str) -> Optional[dict]:
    """
    Extract a JSON object from the LLM response.
    Handles cases where the LLM wraps JSON in markdown fences or adds preamble.
    """
    if not response:
        return None

    text = response.strip()

    # Strip markdown code fences
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try to find JSON object boundaries
    # Find the first { and last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def sanitize_content(content: str) -> str:
    """Remove common LLM preamble patterns from content."""
    # Strip "Here is the wiki article:" type prefixes
    preamble_patterns = [
        r'^Here\s+is\s+the\s+wiki\s+article[:\s]*\n*',
        r'^Here\s+is\s+the\s+JSON[:\s]*\n*',
        r'^#{1,2}\s+' + r'Spirits?\s+(?:One\s+)?Wiki\b.*?\n',
        r'^This\s+is\s+a\s+comprehensive\s+guide.*?\n',
    ]
    for pattern in preamble_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.MULTILINE)
    return content.strip()


# Keep this for backward compatibility with existing pages
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

    clean_content = content[:match.start()] + content[match.end():]
    clean_content = clean_content.strip()

    return metadata, clean_content


# ──────────────────────────────────────────────────────────
# Main synthesis function
# ──────────────────────────────────────────────────────────

def synthesize_wiki_page(
    entity_name: str,
    entity_type: str,
    items: list,
    client: LLMClient,
    max_retries: int = 3,
) -> tuple[str, dict]:
    """
    Use the LLM to write a wiki article from source blocks.
    The LLM outputs structured JSON, which is then converted to markdown.
    Returns (markdown_with_citations, metadata_dict).
    Falls back to structured verbatim layout if LLM fails.
    """
    source_text = format_source_blocks(items)
    ref_lookup = build_ref_lookup(items)
    metadata = {}

    # Choose prompt based on entity type
    if entity_type == "character":
        prompt = CHARACTER_JSON_PROMPT.format(
            entity_name=entity_name,
            source_blocks=source_text,
        )
    elif entity_type == "location":
        prompt = LOCATION_JSON_PROMPT.format(
            entity_name=entity_name,
            source_blocks=source_text,
        )
    else:
        prompt = GENERIC_JSON_PROMPT.format(
            entity_name=entity_name,
            entity_type=entity_type,
            source_blocks=source_text,
        )

    for attempt in range(max_retries):
        try:
            content = client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4000,
                json_mode=True,
            )
            if not content or len(content.strip()) < 20:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                break

            data = extract_json_from_response(content)
            if not data:
                # JSON parse failed — try once more
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                # Last resort: try to use as raw markdown (sanitized)
                content = sanitize_content(content)
                if entity_type == "character":
                    metadata, content = parse_character_metadata(content)
                return content, metadata

            # Convert JSON to markdown based on entity type
            if entity_type == "character":
                md, metadata = character_json_to_markdown(data)
            elif entity_type == "location":
                md, metadata = location_json_to_markdown(data)
            else:
                md, metadata = generic_json_to_markdown(data)

            if md and len(md.strip()) > 30:
                # Post-process: replace any [REF-N] placeholders with actual sources
                md = fix_references(md, ref_lookup)
                return md, metadata

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
