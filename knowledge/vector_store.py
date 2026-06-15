import chromadb
from sentence_transformers import SentenceTransformer
from config import CHROMA_DIR

embedder = SentenceTransformer("pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb")
client = chromadb.PersistentClient(path=str(CHROMA_DIR))

sap_collection = client.get_or_create_collection("sapient_sap_chunks")
ig_collection = client.get_or_create_collection("sapient_ig_chunks")


def embed_ig_document(chunks: list[dict], doc_type: str):
    """
    doc_type: 'adamig' or 'sdtmig'
    """
    for i, chunk in enumerate(chunks):
        embedding = embedder.encode(chunk["text"]).tolist()
        ig_collection.add(
            documents=[chunk["text"]],
            embeddings=[embedding],
            metadatas=[{
                "doc_type": doc_type,
                "section": chunk["section"]
            }],
            ids=[f"{doc_type}_chunk_{i}"]
        )


def query_ig(query: str, doc_type: str, n_results: int = 5) -> list[str]:
    embedding = embedder.encode(query).tolist()
    results = ig_collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        where={"doc_type": doc_type}
    )
    return results["documents"][0]


def query_sap(query: str, study_id: str, n_results: int = 5) -> list[str]:
    embedding = embedder.encode(query).tolist()
    results = sap_collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        where={"study_id": study_id}
    )
    return results["documents"][0]