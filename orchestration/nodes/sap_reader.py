import fitz
import json
import hashlib
from cache.prompt_cache import get_cached, set_cached
from openai import OpenAI
from chromadb import PersistentClient
from orchestration.llm_retry import create_with_retry
from orchestration.state import SapientState
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, REASONING_MODEL, TEMPERATURE, MAX_TOKENS, CHROMA_DIR, COLLECTION_NAME
from config import HF_TOKEN
import os
from knowledge.vector_store import embedder
os.environ["HF_TOKEN"] = HF_TOKEN
client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=60.0)
chroma_client = PersistentClient(path=str(CHROMA_DIR))
collection = chroma_client.get_or_create_collection(COLLECTION_NAME)

SECTION_HEADERS = [
    "objective", "endpoint", "population", "statistical method",
    "analysis", "censoring", "randomization", "visit", "schedule"
]

def extract_chunks(sap_path: str) -> list[dict]:
    doc = fitz.open(sap_path)
    chunks = []
    current_section = "general"
    buffer = []
    for page in doc:
        text = page.get_text()
        for line in text.split("\n"):
            line_lower = line.lower().strip()
            is_header = any(h in line_lower for h in SECTION_HEADERS)
            if is_header and buffer:
                chunks.append({"section": current_section, "text": "\n".join(buffer).strip(), "page": page.number})
                buffer = []
                current_section = line.strip()
            buffer.append(line)
    if buffer:
        chunks.append({"section": current_section, "text": "\n".join(buffer).strip(), "page": page.number})
    return chunks

def embed_chunks(chunks: list[dict], study_id: str):
    print(f"Embedding {len(chunks)} chunks for study_id: {study_id}")
    for i, chunk in enumerate(chunks):
        embedding = embedder.encode(chunk["text"]).tolist()
        collection.add(
            documents=[chunk["text"]],
            embeddings=[embedding],
            metadatas=[{"section": chunk["section"], "study_id": study_id}],
            ids=[f"{study_id}_chunk_{i}"]
        )

def extract_metadata(chunks: list[dict]) -> dict:
    combined = "\n\n".join([c["text"] for c in chunks[:10]])
    print(f"Prompt length: {len(combined)} chars")
    prompt = f"""
You are a clinical programming expert. Extract the following from this SAP excerpt:
- study_id
- compound
- therapeutic_area  
- primary_endpoint
- populations (list)
Return as valid JSON only. No explanation.
SAP TEXT:
{combined}
"""
    cache_key = hashlib.sha256(prompt.encode()).hexdigest()
    content = get_cached(cache_key)
    if content is None:
        response = create_with_retry(client,
            model=REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        content = response.choices[0].message.content
        if content:
            set_cached(cache_key, content)
    text = content.strip().replace("```json", "").replace("```", "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}

def run(state: SapientState) -> SapientState:
    print("sap_reader: starting")
    sap_path = state["sap_path"]
    study_id = state["study_id"]
    print("sap_reader: extracting chunks")
    chunks = extract_chunks(sap_path)
    print(f"sap_reader: {len(chunks)} chunks extracted")
    embed_chunks(chunks, study_id)
    print("sap_reader: chunks embedded")
    metadata = extract_metadata(chunks)
    print(f"sap_reader: metadata extracted: {metadata}")
    return {**state, "sap_chunks": chunks, "study_metadata": metadata, "current_node": "sap_reader"}