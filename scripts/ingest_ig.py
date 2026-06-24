import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from knowledge.document_parser import parse_ig_pdf
from knowledge.vector_store import embed_ig_document

def ingest_igs(adamig_path: str, sdtmig_path: str):
    print("Ingesting ADaMIG...")
    adam_chunks = parse_ig_pdf(adamig_path)
    embed_ig_document(adam_chunks, "adamig")
    print(f"ADaMIG: {len(adam_chunks)} chunks embedded")

    print("Ingesting SDTMIG...")
    sdtm_chunks = parse_ig_pdf(sdtmig_path)
    embed_ig_document(sdtm_chunks, "sdtmig")
    print(f"SDTMIG: {len(sdtm_chunks)} chunks embedded")

    print("Done. IGs loaded into ChromaDB.")

if __name__ == "__main__":
    ingest_igs(
        adamig_path="data/reference/adamig.pdf",
        sdtmig_path="data/reference/sdtmig.pdf"
    )