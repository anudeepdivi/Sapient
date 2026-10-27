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
CODEGEN_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"  # mistral-nemotron EOL 2026-09-28; probed 2026-10-28: 3.9s, correct admiral shape
CODEGEN_FALLBACK_MODEL = "z-ai/glm-5.3-flash"  # probed 2026-10-28: correct but ~70s/call
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

TEMPERATURE = 0
MAX_TOKENS = 16384  # nemotron-3-ultra reasons inside content when thinking is on; 8192 truncated spec-gen
# Structured-output calls run with reasoning off: 8x faster, ~half the tokens (probed 2026-10-28).
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}
# Validator rounds before the regeneration loop gives up. Shared so the validator can
# record that the cap was hit instead of the run ending silently.
MAX_REGENERATIONS = 3

EMBEDDING_MODEL = "pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb"

# Sponsor environment (harness)
SPONSOR_ENV_DIR = Path(os.getenv("SAPIENT_SPONSOR_ENV", BASE_DIR / "sponsor_r_env"))
HARNESS_STATE_DIR = BASE_DIR / "harness_runs"
HARNESS_GENERATOR = os.getenv("SAPIENT_HARNESS_GENERATOR", "stub")