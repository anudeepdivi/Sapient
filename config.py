import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
# Project Root 
BASE_DIR = Path(__file__).parent

# Data Paths 
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SDTM_DIR = DATA_DIR / "sdtm"
# SDTM source for ADaM generation (relative path embedded in generated R programs).
# Default: pharmaversesdtm export. Set SAPIENT_SDTM_DIR=data/sdtm_generated to run
# the full raw->SDTM->ADaM chain on our own generated SDTM (build_sdtm_chain.R).
SDTM_SOURCE = os.getenv("SAPIENT_SDTM_DIR", "data/sdtm")
ADAM_DIR = DATA_DIR / "adam"
SAP_DIR = DATA_DIR / "sap"
REFERENCE_DIR = DATA_DIR / "reference"

# Models
REASONING_MODEL = "google/diffusiongemma-26b-a4b-it"
CODEGEN_MODEL = "mistralai/mistral-nemotron"  # probed - clean admiral R; gemma-4 down, diffusiongemma quality wall
CODEGEN_FALLBACK_MODEL = "google/diffusiongemma-26b-a4b-it"
# API Keys
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
if not NVIDIA_API_KEY:
    raise EnvironmentError("NVIDIA_API_KEY is not set")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

HF_TOKEN = os.getenv("HF_TOKEN", "")
if not HF_TOKEN:
    raise EnvironmentError("HF_TOKEN is not set")

# ChromaDB
CHROMA_DIR = BASE_DIR / "chroma_store"
COLLECTION_NAME = "sapient_sap_chunks"

# Cache
CACHE_DIR = BASE_DIR / "cache_store"

# R Runtime
R_EXECUTABLE = os.getenv("R_EXECUTABLE", "Rscript")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

TEMPERATURE = 0
MAX_TOKENS = 8192

EMBEDDING_MODEL = "pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb"