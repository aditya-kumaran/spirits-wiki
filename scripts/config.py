"""Configuration for the ingestion pipeline."""
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Directories
DOCX_DIR = os.path.join(os.path.dirname(__file__), "..", "wikiInitializationDocuments")

# Classification
MIN_CONFIDENCE = 0.5
MIN_TEXT_LENGTH = 20

# Chunking
MAX_CHUNK_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 50

# Entity types
ENTITY_TYPES = [
    "character", "location", "era", "event", "faction",
    "artifact", "concept", "species", "other"
]

SECTION_TYPES = [
    "overview", "attributes", "relationships", "history",
    "appearances", "abilities", "culture", "geography",
    "timeline", "other"
]
