import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
# ── Project Root ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# ── Data Paths ───────────────────────────────────────────────
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SDTM_DIR = DATA_DIR / "sdtm"
ADAM_DIR = DATA_DIR / "adam"
SAP_DIR = DATA_DIR / "sap"
REFERENCE_DIR = DATA_DIR / "reference"

# ── Models ───────────────────────────────────────────────────
REASONING_MODEL = "gemini-2.5-pro"
CODEGEN_MODEL = "gemma-4-31b-it"

# ── API Keys ─────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    raise EnvironmentError("GEMINI_API_KEY is not set")

# ── ChromaDB ─────────────────────────────────────────────────
CHROMA_DIR = BASE_DIR / "chroma_store"
COLLECTION_NAME = "sapient_sap_chunks"

# ── Cache ────────────────────────────────────────────────────
CACHE_DIR = BASE_DIR / "cache_store"

# ── R Runtime ────────────────────────────────────────────────
R_EXECUTABLE = os.getenv("R_EXECUTABLE", "Rscript")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

TEMPERATURE = 0
MAX_TOKENS = 8192

EMBEDDING_MODEL = "pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb"