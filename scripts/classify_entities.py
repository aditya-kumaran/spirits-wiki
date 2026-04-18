"""
Uses LLM as a classifier ONLY. Never generates wiki content.
Returns structured classification labels for each ContentBlock.
"""
import json
import time
from dataclasses import dataclass
from typing import Optional

from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL


@dataclass
class EntityClassification:
    primary_entity: str
    entity_type: str
    section_type: str
    mentioned_entities: list
    confidence: float


CLASSIFICATION_PROMPT = """You are a strict classifier for fictional world content.
Given a text block from a fictional world document, return ONLY a JSON classification.
Do NOT rewrite, summarize, or paraphrase the text. You must NEVER include the original
text or any rewritten version of it in your response.

Classify the text block:
1. primary_entity: The exact name of the main entity this text is about (as it appears in text). Use the most complete/formal name.
2. entity_type: One of [character, location, era, event, faction, artifact, concept, species, other]
3. section_type: One of [overview, attributes, relationships, history, appearances, abilities, culture, geography, timeline, other]
4. mentioned_entities: List of other named entities mentioned in the text (proper nouns only)
5. confidence: Your confidence from 0.0 to 1.0

Text block:
\"\"\"
{text}
\"\"\"

Context -- this text appears under these headings: {heading_path}

Respond with ONLY valid JSON. No other text. Example format:
{{"primary_entity": "Name", "entity_type": "character", "section_type": "overview", "mentioned_entities": ["Other Name"], "confidence": 0.8}}"""


def classify_block(
    block,
    client: Optional[Groq] = None,
    model: str = GROQ_MODEL,
    max_retries: int = 3,
) -> Optional[EntityClassification]:
    """
    Classify a content block using the LLM.
    The LLM returns ONLY classification labels -- never content.
    """
    if client is None:
        client = Groq(api_key=GROQ_API_KEY)

    heading_str = " > ".join(block.heading_path) if block.heading_path else "(no heading context)"
    prompt = CLASSIFICATION_PROMPT.format(
        text=block.text[:2000],  # Truncate very long blocks
        heading_path=heading_str,
    )

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            return EntityClassification(
                primary_entity=result.get("primary_entity", "Unknown"),
                entity_type=result.get("entity_type", "other"),
                section_type=result.get("section_type", "other"),
                mentioned_entities=result.get("mentioned_entities", []),
                confidence=result.get("confidence", 0.0),
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


def classify_blocks_batch(blocks, client=None, model=GROQ_MODEL):
    """Classify a list of blocks, yielding (block, classification) pairs."""
    if client is None:
        client = Groq(api_key=GROQ_API_KEY)

    for i, block in enumerate(blocks):
        # Skip very short blocks and headings that are just titles
        if len(block.text.strip()) < 20:
            continue
        if block.block_type == "heading" and len(block.text.split()) <= 5:
            continue

        classification = classify_block(block, client, model)
        if classification and classification.confidence >= 0.4:
            yield block, classification

        # Rate limiting: Groq free tier has limits
        if i > 0 and i % 25 == 0:
            time.sleep(2)
