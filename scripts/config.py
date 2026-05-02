"""Configuration for the ingestion pipeline."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Auto-load .env and .env.local from the project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env.local", override=True)
load_dotenv(_project_root / ".env", override=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# LLM Provider: "groq" (cloud, rate-limited) or "ollama" (local, no limits)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

# Groq settings (used when LLM_PROVIDER=groq)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Ollama settings (used when LLM_PROVIDER=ollama)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

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
