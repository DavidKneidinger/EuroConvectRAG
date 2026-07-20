"""
ESTOFEX Document Parser and Metadata Extractor.

Parses text headers, timestamps, section blocks, and extracts structured
metadata (threat levels, regions, hazards, storm modes) for dual-engine ingestion.
"""

import glob
import os
import re
from datetime import datetime


def parse_estofex_datetime(date_str):
    """Convert ESTOFEX date string to ISO datetime string."""
    clean_str = re.sub(r'\s+', ' ', date_str.strip())
    clean_str = re.sub(r'^[A-Za-z]{3}\s+', '', clean_str)

    date_formats = [
        "%d %b %Y %H:%M",
        "%d %B %Y %H:%M",
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue

    return None


def extract_threat_level(content):
    """Extract highest threat level (0, 1, 2, 3) from ESTOFEX report."""
    if re.search(r'level\s*3', content, re.IGNORECASE):
        return 3
    elif re.search(r'level\s*2', content, re.IGNORECASE):
        return 2
    elif re.search(r'level\s*1', content, re.IGNORECASE):
        return 1
    return 0


def extract_regions(content):
    """Match key European forecast regions."""
    known_regions = [
        "Po Valley", "N Italy", "S Italy", "Italy", "Alps", "Pannonian Basin",
        "Germany", "France", "Spain", "Poland", "Czech Republic", "Austria",
        "Switzerland", "Benelux", "Balkans", "Slovenia", "Croatia", "Hungary",
        "Romania", "Slovakia", "Adriatic", "Iberian Peninsula"
    ]
    found = []
    for r in known_regions:
        if re.search(r'\b' + re.escape(r) + r'\b', content, re.IGNORECASE):
            found.append(r)
    return found


def extract_hazards(content):
    """Extract severe weather hazards mentioned."""
    hazards_map = {
        "Large Hail": [r"large hail", r"very large hail", r"giant hail"],
        "Severe Winds": [r"severe wind", r"damaging wind", r"severe gust", r"squall"],
        "Tornado": [r"tornado", r"tornadic", r"waterspout"],
        "Excessive Rainfall": [r"excessive rain", r"heavy rain", r"flash flood"]
    }
    found = []
    for hazard, patterns in hazards_map.items():
        if any(re.search(p, content, re.IGNORECASE) for p in patterns):
            found.append(hazard)
    return found


def extract_storm_modes(content):
    """Extract storm modes mentioned."""
    modes_map = {
        "Supercell": [r"supercell", r"supercells"],
        "MCS": [r"\bmcs\b", r"mesoscale convective system"],
        "QLCS": [r"\bqlcs\b", r"quasi-linear"],
        "Multicell": [r"multicell", r"multi-cell"]
    }
    found = []
    for mode, patterns in modes_map.items():
        if any(re.search(p, content, re.IGNORECASE) for p in patterns):
            found.append(mode)
    return found


def parse_document(file_path):
    """Parse a single ESTOFEX text file into a structured metadata dictionary."""
    filename = os.path.basename(file_path)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    is_md = "Mesoscale Discussion" in content[:200]
    doc_type = "Mesoscale Discussion" if is_md else "Storm Forecast"

    forecaster = "UNKNOWN"
    forecaster_match = re.search(r'Forecaster:\s*([A-Z\s\/]+)', content, re.IGNORECASE)
    if forecaster_match:
        forecaster = forecaster_match.group(1).strip().split('\n')[0]

    valid_start_dt = None
    valid_end_dt = None

    valid_match = re.search(
        r'Valid:\s*([A-Za-z0-9\s:]+)\s+to\s+([A-Za-z0-9\s:]+?)(?:\s*UTC|\s*Issued|\n)',
        content,
        re.IGNORECASE
    )

    if valid_match:
        valid_start_dt = parse_estofex_datetime(valid_match.group(1))
        valid_end_dt = parse_estofex_datetime(valid_match.group(2))

    issued_dt = None
    issued_match = re.search(r'Issued:\s*([A-Za-z0-9\s:]+?)(?:\n|\r|\Z)', content, re.IGNORECASE)
    if issued_match:
        issued_dt = parse_estofex_datetime(issued_match.group(1))

    if not valid_start_dt:
        file_date_match = re.match(r'^(\d{8})', filename)
        if file_date_match:
            try:
                valid_start_dt = datetime.strptime(file_date_match.group(1), "%Y%m%d")
            except ValueError:
                pass

    synopsis_text = ""
    if not is_md:
        synopsis_match = re.search(
            r'SYNOPSIS\s*\n\n?(.*?)(?=\n\n[A-Z\s]{4,}|\n\n\.\.\.|\Z)',
            content,
            re.DOTALL
        )
        if synopsis_match:
            synopsis_text = synopsis_match.group(1).strip()

    return {
        "filename": filename,
        "file_path": file_path,
        "doc_type": doc_type,
        "forecaster": forecaster,
        "valid_start": valid_start_dt.isoformat() if valid_start_dt else "UNKNOWN",
        "valid_end": valid_end_dt.isoformat() if valid_end_dt else "UNKNOWN",
        "valid_start_dt": valid_start_dt,
        "valid_end_dt": valid_end_dt,
        "issued_dt": issued_dt,
        "synopsis": synopsis_text,
        "threat_level": extract_threat_level(content),
        "regions": extract_regions(content),
        "hazards": extract_hazards(content),
        "storm_modes": extract_storm_modes(content),
        "full_text": content
    }


def build_catalog(data_dir):
    """Pass 1: Scan raw text files and return catalog with linked MD synoptic headers."""
    search_path = os.path.join(data_dir, "*", "*.txt")
    file_paths = glob.glob(search_path)

    print(f"Parsing metadata across {len(file_paths)} documents...")
    parsed_docs = [parse_document(fp) for fp in file_paths]

    main_forecasts = [d for d in parsed_docs if d["doc_type"] == "Storm Forecast"]
    ms_discussions = [d for d in parsed_docs if d["doc_type"] == "Mesoscale Discussion"]

    for md in ms_discussions:
        md_time = md["issued_dt"] or md["valid_start_dt"]
        if not md_time:
            continue

        parent_synopsis = "NO PARENT SYNOPSIS FOUND"
        parent_filename = "NONE"

        for main_fcst in main_forecasts:
            if main_fcst["valid_start_dt"] and main_fcst["valid_end_dt"]:
                if main_fcst["valid_start_dt"] <= md_time <= main_fcst["valid_end_dt"]:
                    parent_synopsis = main_fcst["synopsis"]
                    parent_filename = main_fcst["filename"]
                    break

        md["parent_synopsis"] = parent_synopsis
        md["parent_filename"] = parent_filename

    return parsed_docs