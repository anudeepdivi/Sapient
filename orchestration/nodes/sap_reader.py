import fitz
import json
import google.generativeai as genai
from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
from orchestration.state import SapientState
from config import GEMINI_API_KEY, REASONING_MODEL, CHROMA_DIR, COLLECTION_NAME

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(REASONING_MODEL)
embedder = SentenceTransformer("pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb")
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
                chunks.append({
                    "section": current_section,
                    "text": "\n".join(buffer).strip(),
                    "page": page.number
                })
                buffer = []
                current_section = line.strip()

            buffer.append(line)

    if buffer:
        chunks.append({
            "section": current_section,
            "text": "\n".join(buffer).strip(),
            "page": page.number
        })

    return chunks


def embed_chunks(chunks: list[dict], study_id: str):
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

    response = model.generate_content(prompt)
    text = response.text.strip().replace("```json", "").replace("```", "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def run(state: SapientState) -> SapientState:
    sap_path = state["sap_path"]
    study_id = state["study_id"]

    chunks = extract_chunks(sap_path)
    embed_chunks(chunks, study_id)
    metadata = extract_metadata(chunks)

    return {
        **state,
        "sap_chunks": chunks,
        "study_metadata": metadata,
        "current_node": "sap_reader"
    }