# EuroConvectRAG

**EuroConvectRAG** is an event-aware, dual-engine Retrieval-Augmented Generation (RAG) system designed to analyze and synthesize 20+ years of severe convective storm forecast bulletins from the European Storm Forecast Experiment ([ESTOFEX](https://www.estofex.org/)).

By combining a **structured SQLite metadata database** for exact statistical queries with a **ChromaDB vector store** for qualitative synoptic reasoning, the system eliminates hallucinations across full-corpus frequency questions while providing deep physical synthesis via local Ollama LLMs.

---

## 🏛️ System Architecture

```
                                  [ USER QUERY ]
                                        │
           ┌────────────────────────────┴────────────────────────────┐
           ▼                                                         ▼
  [ STATISTICAL / FREQUENCY ]                               [ PHYSICAL / SYNOPTIC ]
"How often do MCSs occur in..."                        "What mechanisms cause EML caps..."
           │                                                         │
           ▼                                                         ▼
   [ SQL METADATA ENGINE ]                                 [ VECTOR RAG ENGINE ]
  SQLite (`data/forecasts.db`)                         ChromaDB (`data/vector_db/`)
  100% exact corpus counts across                        Sub-query expansion & semantic
  threat levels, regions, & modes                       retrieval of report contexts
           │                                                         │
           └────────────────────────────┬────────────────────────────┘
                                        ▼
                            [ OLLAMA LLM SYNTHESIS ]
                    `llama3.2:3b` (Local) / `qwen2.5:32b` (Server)
```

---

## 📂 Project Structure

```text
EuroConvectRAG/
├── data/                       # Local data directory (Git-ignored)
│   ├── raw_forecasts/          # Scraped raw text bulletins (YYYY/*.txt)
│   ├── forecasts.db            # SQLite metadata database (counts, levels, regions)
│   └── vector_db/              # Persistent ChromaDB vector index
├── src/
│   ├── scraper.py              # ESTOFEX web scraper & bulletin downloader
│   ├── parser.py               # Metadata extractor (levels, hazards, regions, modes)
│   ├── db.py                   # SQLite database schema & batch upsert manager
│   ├── embed.py                # Fast batch embedding & dual-engine indexer
│   └── query.py                # Hybrid query engine with automatic SQL/RAG routing
├── .gitignore
├── environment.yml             # Mamba environment specification
└── README.md
```

---

## Installation & Setup

### 1. Clone & Environment Creation

```bash
git clone <your-repo-url>
cd EuroConvectRAG

# Create environment using Mamba or Conda
mamba env create -f environment.yml
mamba activate euroconvect_rag
```

### 2. Local Ollama Setup

Install Ollama and pull the lightweight 3B model for local CPU development:

```bash
# Install Ollama (Linux)
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh

# Pull lightweight model for laptop testing
ollama pull llama3.2:3b
```

---

## Execution Workflow

### Step 1: Scrape Bulletins
Download raw ESTOFEX forecast bulletins and mesoscale discussions:
```bash
python3 src/scraper.py
```

### Step 2: Build Dual Database (SQLite + ChromaDB)
Index all report text into SQLite and ChromaDB simultaneously:
```bash
python3 src/embed.py
```

### Step 3: Query the System

#### Statistical Queries (SQL Route)
Executes exact SQL aggregations over the entire corpus with 0% hallucination:
```bash
python3 src/query.py "How often do MCSs form in the Po Valley?" llama3.2:3b
```

#### Physical Synthesis Queries (Vector RAG Route)
Performs sub-query expansion, retrieves contextual report chunks, and streams meteorological synthesis:
```bash
python3 src/query.py "What ingredients distinguish supercells from MCSs in the Po Valley?" llama3.2:3b
```

---

## Institute Server Deployment

For large-corpus analysis on server:

1. **User-Space Ollama Installation (No Root):**
   ```bash
   mkdir -p ~/.local/bin
   curl -L [https://ollama.com/download/ollama-linux-amd64.tar.gz](https://ollama.com/download/ollama-linux-amd64.tar.gz) | tar -xz -C ~/.local/
   ```

2. **Serve High-Capacity Model:**
   ```bash
   tmux new -s ollama
   OLLAMA_HOST=0.0.0.0:11434 ollama serve
   # Detach with Ctrl+B, D

   ollama pull qwen2.5:32b
   ```

3. **Run Query with Server Model:**
   ```bash
   python3 src/query.py "Explain the interaction of EML advection and CAPE over northern Italy" qwen2.5:32b
   ```
