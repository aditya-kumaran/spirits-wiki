"""
Uses LLM as a classifier ONLY. Never generates wiki content.
Returns structured classification labels for each ContentBlock.
Supports both Groq (cloud) and Ollama (local) via LLMClient.

Key feature: Pronoun resolution — the LLM resolves all pronouns (he, she, they, etc.)
to their named entity referents using heading context, so no information is lost.
A single block can be attributed to multiple entities.
"""
import json
import time
from dataclasses import dataclass
from typing import Optional

from llm_client import LLMClient


PRONOUNS = {
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "they", "them", "their", "theirs", "themselves",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
}


@dataclass
class EntityClassification:
    primary_entity: str
    entity_type: str
    section_type: str
    mentioned_entities: list
    confidence: float
    # Entities this block contains relevant information about (including primary)
    # Used for multi-entity attribution — one block can feed into multiple pages
    relevant_entities: list


CLASSIFICATION_PROMPT = """You are a strict classifier for fictional world content.
Given a text block from a fictional world document, return ONLY a JSON classification.
Do NOT rewrite, summarize, or paraphrase the text. You must NEVER include the original
text or any rewritten version of it in your response.

CRITICAL — PRONOUN RESOLUTION:
The text may contain pronouns (he, she, they, him, her, etc.) that refer to named characters.
You MUST resolve these pronouns to the actual character names using the heading context and
surrounding clues. For example, if the heading says "Catherine" and the text says "she went
to Dubai", you must identify that "she" = Catherine.

When multiple characters are involved (e.g., "she injured him"), resolve ALL pronouns:
identify who "she" and "him" refer to. Include ALL characters that the text contains
meaningful information about in the "relevant_entities" field.

NEVER use a pronoun as an entity name. Always use the actual character/entity name.

Classify the text block:
1. primary_entity: The main entity this text is about (resolve pronouns to actual names). Use the most complete/formal name as it appears in the document.
2. entity_type: One of [character, location, era, event, faction, artifact, concept, species, other]
3. section_type: One of [overview, attributes, relationships, history, appearances, abilities, culture, geography, timeline, other]
4. mentioned_entities: List of ALL other named entities mentioned or referenced by pronoun in the text (proper nouns only, pronouns resolved to names)
5. relevant_entities: List of ALL entity names (including primary_entity) that this text contains important information about. If "she injured him" and she=Catherine, him=Jacob, then BOTH Catherine and Jacob should be listed because the text is relevant to both their pages.
6. confidence: Your confidence from 0.0 to 1.0

Text block:
\"\"\"
{text}
\"\"\"

Context — this text appears under these headings: {heading_path}

Respond with ONLY valid JSON. No other text. Example:
{{"primary_entity": "Catherine", "entity_type": "character", "section_type": "history", "mentioned_entities": ["Jacob", "Dubai", "Singapore"], "relevant_entities": ["Catherine", "Jacob"], "confidence": 0.85}}"""


def is_pronoun(name: str) -> bool:
    """Check if a name is actually a pronoun."""
    return name.lower().strip() in PRONOUNS


def classify_block(
    block,
    client: LLMClient,
    max_retries: int = 3,
) -> Optional[EntityClassification]:
    """
    Classify a content block using the LLM.
    The LLM returns ONLY classification labels — never content.
    Pronouns are resolved to actual entity names.
    """
    heading_str = " > ".join(block.heading_path) if block.heading_path else "(no heading context)"
    prompt = CLASSIFICATION_PROMPT.format(
        text=block.text[:2000],  # Truncate very long blocks
        heading_path=heading_str,
    )

    for attempt in range(max_retries):
        try:
            content = client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=400,
                json_mode=True,
            )

            if not content:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None

            result = json.loads(content)

            primary = result.get("primary_entity", "Unknown")
            mentioned = result.get("mentioned_entities", [])
            relevant = result.get("relevant_entities", [])

            # Filter out any pronouns that slipped through
            if is_pronoun(primary):
                # Try to use heading context as the entity name
                if block.heading_path:
                    primary = block.heading_path[-1]
                else:
                    primary = "Unknown"

            mentioned = [e for e in mentioned if not is_pronoun(e)]
            relevant = [e for e in relevant if not is_pronoun(e)]

            # Ensure primary is in relevant_entities
            if primary and primary != "Unknown" and primary not in relevant:
                relevant.insert(0, primary)

            # If relevant_entities is empty, default to just primary
            if not relevant and primary and primary != "Unknown":
                relevant = [primary]

            return EntityClassification(
                primary_entity=primary,
                entity_type=result.get("entity_type", "other"),
                section_type=result.get("section_type", "other"),
                mentioned_entities=mentioned,
                confidence=result.get("confidence", 0.0),
                relevant_entities=relevant,
            )
        except json.JSONDecodeError:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            return None
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait_time = 2 ** attempt * 2
                print(f"    Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            print(f"  Classification failed for paragraph {block.paragraph_index}: {e}")
            return None

    return None
