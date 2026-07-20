"""
ESTOFEX Structured Metadata Database Manager.
"""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "data", "forecasts.db")


def init_db():
    """Initialize the SQLite database schema and indexes."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE,
        doc_type TEXT,
        issued_dt TEXT,
        valid_start TEXT,
        valid_end TEXT,
        year INTEGER,
        forecaster TEXT,
        threat_level INTEGER,
        regions TEXT,
        hazards TEXT,
        storm_modes TEXT,
        synopsis TEXT
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_year ON forecasts(year);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_type ON forecasts(doc_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_threat_level ON forecasts(threat_level);")

    conn.commit()
    conn.close()


def upsert_forecasts_batch(docs):
    """Insert or update all forecast records in a single fast SQL transaction."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    records = []
    for doc in docs:
        year_val = doc["valid_start_dt"].year if doc.get("valid_start_dt") else None
        records.append((
            doc["filename"],
            doc["doc_type"],
            doc["issued_dt"].isoformat() if doc.get("issued_dt") else None,
            doc["valid_start"],
            doc["valid_end"],
            year_val,
            doc["forecaster"],
            doc["threat_level"],
            ",".join(doc["regions"]),
            ",".join(doc["hazards"]),
            ",".join(doc["storm_modes"]),
            doc["synopsis"]
        ))

    cursor.executemany("""
    INSERT INTO forecasts (
        filename, doc_type, issued_dt, valid_start, valid_end,
        year, forecaster, threat_level, regions, hazards, storm_modes, synopsis
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(filename) DO UPDATE SET
        doc_type=excluded.doc_type,
        issued_dt=excluded.issued_dt,
        valid_start=excluded.valid_start,
        valid_end=excluded.valid_end,
        year=excluded.year,
        forecaster=excluded.forecaster,
        threat_level=excluded.threat_level,
        regions=excluded.regions,
        hazards=excluded.hazards,
        storm_modes=excluded.storm_modes,
        synopsis=excluded.synopsis
    """, records)

    conn.commit()
    conn.close()