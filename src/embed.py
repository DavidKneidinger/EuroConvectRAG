"""
ESTOFEX Fast Event-Aware Vector & SQL Ingestion Script.
"""

import os
import torch
from sentence_transformers import SentenceTransformer
import chromadb
from parser import build_catalog
from db import init_db, upsert_forecasts_batch

# Set PyTorch to use all available CPU cores
torch.set_num_threads(os.cpu_count() or 4)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data", "raw_forecasts")
DB_DIR = os.path.join(BASE_DIR, "..", "data", "vector_db")

# Load embedding model directly for fast batch encoding
EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")


def chunk_text(text, chunk_size=900, overlap=100):
    """Split text into paragraph chunks with overlap."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) < chunk_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = current_chunk[-overlap:] + para + "\n\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def build_event_database():
    """Build persistent ChromaDB collection and SQLite database simultaneously."""
    init_db()

    print(f"Initializing ChromaDB storage at: {DB_DIR}")
    client = chromadb.PersistentClient(path=DB_DIR)

    collection = client.get_or_create_collection(
        name="estofex_forecasts",
        metadata={"hnsw:space": "cosine"}
    )

    docs = build_catalog(DATA_DIR)
    
    # 1. Fast Single-Transaction SQLite Upload
    print(f"Batch writing {len(docs)} document records to SQLite...")
    upsert_forecasts_batch(docs)

    documents = []
    metadatas = []
    ids = []

    # 2. Build Chunks
    for doc in docs:
        filename = doc["filename"]
        doc_type = doc["doc_type"]
        valid_start = doc["valid_start"]
        valid_end = doc["valid_end"]
        forecaster = doc["forecaster"]

        synopsis_header = doc["synopsis"] if doc_type == "Storm Forecast" else doc.get("parent_synopsis", "")
        if synopsis_header:
            synopsis_header = synopsis_header[:400] + "..." if len(synopsis_header) > 400 else synopsis_header
        else:
            synopsis_header = "N/A"

        chunks = chunk_text(doc["full_text"])

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{filename}_{idx}"

            context_banner = (
                f"=== ESTOFEX REPORT METADATA ===\n"
                f"FILE: {filename} | TYPE: {doc_type} | FORECASTER: {forecaster}\n"
                f"VALID: {valid_start} TO {valid_end}\n"
                f"SYNOPTIC BACKDROP: {synopsis_header}\n"
                f"================================\n\n"
                f"{chunk}"
            )

            meta = {
                "filename": filename,
                "doc_type": doc_type,
                "forecaster": forecaster,
                "valid_start": valid_start,
                "valid_end": valid_end,
                "year": str(doc["valid_start_dt"].year) if doc.get("valid_start_dt") else "UNKNOWN"
            }

            documents.append(context_banner)
            metadatas.append(meta)
            ids.append(chunk_id)

    total_chunks = len(documents)
    print(f"Generated {total_chunks} chunks. Pre-computing embeddings in large batches...")

    # 3. High-Speed Pre-computed Embeddings
    embeddings = EMBED_MODEL.encode(
        documents,
        batch_size=128,
        show_progress_bar=True,
        convert_to_numpy=True
    ).tolist()

    # 4. Fast ChromaDB Vector Upsert
    batch_size = 1000
    print(f"Upserting {total_chunks} vector embeddings to ChromaDB...")

    for i in range(0, total_chunks, batch_size):
        end_idx = i + batch_size
        collection.upsert(
            ids=ids[i:end_idx],
            documents=documents[i:end_idx],
            embeddings=embeddings[i:end_idx],
            metadatas=metadatas[i:end_idx]
        )

    print("Dual-database ingestion (SQLite + ChromaDB) complete.")


if __name__ == "__main__":
    build_event_database()