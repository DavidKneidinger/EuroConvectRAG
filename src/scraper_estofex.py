"""
ESTOFEX Forecast Scraper Engine.

Retrieves historical convective storm forecasts and mesoscale discussions
from the ESTOFEX archive, parses HTML into 
clean plain text, and organizes output into yearly directories.
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.estofex.org/cgi-bin/polygon/showforecast.cgi"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw_forecasts")


def ensure_data_directory():
    """Ensure base data destination directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def fetch_forecast_filenames():
    """
    Fetch the master archive list from ESTOFEX.

    Returns:
        list: Sorted list of XML forecast filenames.
    """
    master_url = f"{BASE_URL}?list=yes&all=yes"
    print(f"Connecting to ESTOFEX archive: {master_url}")
    
    response = requests.get(master_url, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    filenames = set()

    for link in soup.find_all('a', href=True):
        match = re.search(r'fcstfile=([a-zA-Z0-9_]+\.xml)', link['href'])
        if match:
            filenames.add(match.group(1))

    return sorted(list(filenames))


def parse_html_to_plain_text(html_content):
    """
    Extract clean bulletin text from ESTOFEX HTML response.

    Args:
        html_content (str): Raw HTML string from server.

    Returns:
        str: Cleaned plain text document.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove script, style, head, links, and image elements
    for element in soup(["script", "style", "head", "noscript", "a", "img"]):
        element.decompose()

    blocks = soup.find_all(['div', 'p'], class_=['title', 'bulletin'])
    extracted_text = []

    for block in blocks:
        for br in block.find_all(['br', 'br/']):
            br.replace_with('\n')
        
        text = block.get_text().strip()
        if text:
            extracted_text.append(text)

    return "\n\n".join(extracted_text)


def download_forecast(filename, overwrite=False):
    """
    Download and clean an individual forecast file, saving it into a yearly directory.

    Args:
        filename (str): XML forecast filename (e.g., '200601151200_1_stormforecast.xml').
        overwrite (bool): Force overwrite if file exists locally.
    """
    year_match = re.match(r'^(\d{4})', filename)
    if not year_match:
        print(f"Skipping malformed filename: {filename}")
        return

    year = year_match.group(1)
    year_dir = os.path.join(DATA_DIR, year)
    os.makedirs(year_dir, exist_ok=True)

    target_url = f"{BASE_URL}?text=yes&fcstfile={filename}"
    out_filename = filename.replace('.xml', '.txt')
    out_path = os.path.join(year_dir, out_filename)

    if os.path.exists(out_path) and not overwrite:
        return

    try:
        response = requests.get(target_url, timeout=10)
        response.raise_for_status()

        clean_text = parse_html_to_plain_text(response.text)

        if clean_text:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(clean_text)
            print(f"Saved [{year}]: {out_filename}")
        else:
            print(f"Warning: Empty content for {filename}")

        time.sleep(0.2)  # Polite request throttling

    except requests.RequestException as err:
        print(f"Failed {filename}: {err}")


def main():
    """Execute download pipeline for all year-round forecasts."""
    ensure_data_directory()
    all_files = fetch_forecast_filenames()
    print(f"Found {len(all_files)} total forecast entries across all seasons.")

    print("Starting download pipeline...")
    for idx, fname in enumerate(all_files, start=1):
        download_forecast(fname, overwrite=False)
        if idx % 100 == 0:
            print(f"Progress: {idx}/{len(all_files)} files processed.")

    print("All year-round forecast downloads complete.")


if __name__ == "__main__":
    main()