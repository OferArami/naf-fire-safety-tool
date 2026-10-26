"""
Shared paths for the update pipeline (data.gov.il route).
The old gov.il "Shalhevet" route and its settings live in archive_old_govil_route/.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OPENDATA_DIR = BASE_DIR / "opendata"                  # permit.json, business.json, opendata_meta.json
OUTPUT_DIR = BASE_DIR / "output"
BUILD_REPORT_FILE = OUTPUT_DIR / "build_report.json"  # written by 03b, read by 04 (dates) and run_update
DIFF_REPORT_FILE = OUTPUT_DIR / "diff_report.txt"     # written by 05

SITE_DIR = OUTPUT_DIR / "site"           # the folder whose contents go into the GitHub repo
SITE_DATA_DIR = SITE_DIR / "data"        # one group_<g>.json per group
SITE_INDEX_FILE = SITE_DIR / "index.html"
SITE_TEMPLATE_FILE = BASE_DIR.parent / "site_template.html"


def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
