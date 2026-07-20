"""
ESTOFEX Dual-Engine Hybrid Query System (SQL + ChromaDB).

Routes statistical/frequency queries to SQLite for 100% exact corpus counts,
and physical/synoptic questions to ChromaDB for grounded LLM synthesis.
"""

import os
import re
import sqlite3

os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import chromadb
from chromadb.utils import embedding_functions
import ollama

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_DB_PATH = os.path.join(BASE_DIR, "..", "data", "forecasts.db")
VECTOR_DB_DIR = os.path.join(BASE_DIR, "..", "data", "vector_db")

EMBED_FN = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

SYSTEM_PROMPT = """You are an elite European synoptic meteorologist and severe convective storm research partner.

Your role is to synthesize physical mechanisms, synoptic setups, and mesoscale processes across historical ESTOFEX reports.

GLOSSARY OF ACRONYMS:
- EML: Elevated Mixed Layer (hot, dry mid-level air mass with steep lapse rates)
- CAPE / CIN: Convective Available Potential Energy / Convective Inhibition
- DLS: Deep Layer Shear (0-6 km bulk shear)
- LLS / SREH: Low-Level Shear (0-1 km) / Storm-Relative Environmental Helicity
- MCS / QLCS: Mesoscale Convective System / Quasi-Linear Convective System

INSTRUCTIONS:
1. Base your response strictly on the provided context and SQL statistics.
2. Rely on established atmospheric thermodynamics and dynamics principles to explain the physical reasoning.
3. NEVER fabricate or assume events, values, or outcomes not supported by the context.
4. Always cite specific dates, forecasters, and report details when discussing specific atmospheric features.
"""


def is_statistical_query(query):
    """Detect if query asks for corpus counts, frequency, or statistical totals."""
    stats_keywords = [
        "how many", "how often", "count", "frequency", "total number",
        "breakdown", "statistics", "distribution", "how frequently"
    ]
    return any(kw in query.lower() for kw in stats_keywords)


def query_sql_corpus(query):
    """Run exact statistical aggregations on the SQLite metadata database."""
    conn = sqlite3.connect(SQL_DB_PATH)
    cursor = conn.cursor()

    # Extract filter conditions from query
    region = None
    known_regions = ["Po Valley", "N Italy", "Italy", "Alps", "Pannonian Basin", "Germany", "France", "Spain", "Austria"]
    for r in known_regions:
        if re.search(r'\b' + re.escape(r) + r'\b', query, re.IGNORECASE):
            region = r
            break

    mode = None
    known_modes = ["MCS", "Supercell", "QLCS", "Multicell"]
    for m in known_modes:
        if re.search(r'\b' + re.escape(m) + r'\b', query, re.IGNORECASE):
            mode = m
            break

    threat_level = None
    level_match = re.search(r'level\s*([0-3])', query, re.IGNORECASE)
    if level_match:
        threat_level = int(level_match.group(1))

    # Build SQL Query
    conditions = []
    params = []

    if region:
        conditions.append("regions LIKE ?")
        params.append(f"%{region}%")
    if mode:
        conditions.append("storm_modes LIKE ?")
        params.append(f"%{mode}%")
    if threat_level is not None:
        conditions.append("threat_level = ?")
        params.append(threat_level)

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Total count query
    count_sql = f"SELECT COUNT(*) FROM forecasts{where_clause}"
    cursor.execute(count_sql, params)
    total_matches = cursor.fetchone()[0]

    # Year breakdown query
    year_sql = f"SELECT year, COUNT(*) FROM forecasts{where_clause} GROUP BY year ORDER BY year"
    cursor.execute(year_sql, params)
    year_distribution = cursor.fetchall()

    conn.close()

    return {
        "region": region or "All Regions",
        "mode": mode or "All Modes",
        "threat_level": threat_level if threat_level is not None else "All Levels",
        "total_matches": total_matches,
        "year_distribution": year_distribution
    }


def get_chroma_collection():
    """Connect to persistent ChromaDB instance."""
    client = chromadb.PersistentClient(path=VECTOR_DB_DIR)
    return client.get_collection(
        name="estofex_forecasts",
        embedding_function=EMBED_FN
    )


def retrieve_decomposed_context(user_query, collection, n_results_per_query=3):
    """Sub-query expansion for comparative and multi-concept questions."""
    queries = [user_query]

    if "difference" in user_query.lower() or "versus" in user_query.lower() or "vs" in user_query.lower():
        queries.append(f"{user_query} supercells discrete shear CAPE")
        queries.append(f"{user_query} MCS linear convective system upscale growth cold pool")

    all_chunks, all_metas, seen_ids = [], [], set()

    for q in queries:
        results = collection.query(query_texts=[q], n_results=n_results_per_query)
        chunks = results["documents"][0]
        metas = results["metadatas"][0]
        ids = results["ids"][0]

        for chunk, meta, cid in zip(chunks, metas, ids):
            if cid not in seen_ids:
                seen_ids.add(cid)
                all_chunks.append(chunk)
                all_metas.append(meta)

    return all_chunks, all_metas


def query_storm_expert(user_query, model_name="llama3.2:3b"):
    """Main query pipeline with SQL statistical routing and Vector RAG synthesis."""
    
    # 1. Handle Statistical / Frequency Queries via SQLite
    if is_statistical_query(user_query):
        print(f"\n[QUERY ROUTE: SQL STATISTICAL ENGINE]")
        stats = query_sql_corpus(user_query)

        print(f"\n=== EXACT CORPUS STATISTICS (SQLite) ===")
        print(f"Filter Criteria : Region='{stats['region']}' | Mode='{stats['mode']}' | Threat='{stats['threat_level']}'")
        print(f"Total Matches   : {stats['total_matches']} ESTOFEX forecast reports")
        print("\nYearly Distribution:")
        for yr, cnt in stats['year_distribution']:
            if yr:
                print(f"  - {yr}: {cnt} reports")
        print("=========================================\n")

        # Pass exact stats to LLM to summarize
        prompt = (
            f"=== EXACT METADATA STATISTICS ===\n"
            f"Region: {stats['region']}\n"
            f"Storm Mode: {stats['mode']}\n"
            f"Threat Level: {stats['threat_level']}\n"
            f"Total Matching Forecast Reports: {stats['total_matches']}\n"
            f"Yearly Breakdown: {dict(stats['year_distribution'])}\n\n"
            f"=== USER RESEARCH QUESTION ===\n"
            f"{user_query}"
        )
    
    # 2. Handle Qualitative / Physical Synthesis Queries via Vector DB
    else:
        print(f"\n[QUERY ROUTE: VECTOR RAG SYNTHESIS ENGINE]")
        collection = get_chroma_collection()
        retrieved_chunks, retrieved_meta = retrieve_decomposed_context(user_query, collection)

        if not retrieved_chunks:
            print("No matching forecast records found in vector database.")
            return

        context_str = "\n\n".join(retrieved_chunks)

        print("\n--- RETRIEVED CONTEXT SOURCES ---")
        seen_sources = set()
        for meta in retrieved_meta:
            source_id = f"{meta['filename']} ({meta['doc_type']} by {meta['forecaster']})"
            if source_id not in seen_sources:
                seen_sources.add(source_id)
                print(f" - {source_id} [Valid: {meta['valid_start']}]")
        print("---------------------------------\n")

        prompt = (
            f"=== CONTEXT DOCUMENTS ===\n"
            f"{context_str}\n\n"
            f"=== USER RESEARCH QUESTION ===\n"
            f"{user_query}"
        )

    # 3. Stream Synthesis Response from Ollama
    print(f"Synthesizing response with local model ({model_name})...\n")

    try:
        response_stream = ollama.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            stream=True
        )
        
        print("=== EXPERT SYNTHESIS ===")
        for chunk in response_stream:
            print(chunk['message']['content'], end='', flush=True)
        print("\n========================\n")

    except Exception as err:
        print(f"Error querying Ollama: {err}")


if __name__ == "__main__":
    import sys
    
    query = sys.argv[1]
    model = sys.argv[2] 
    
    query_storm_expert(query, model_name=model)