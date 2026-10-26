"""
Shared constants and small helpers used across every stage of the update pipeline.
Kept in one place so a change to a URL or a file path only has to happen once.
"""
from pathlib import Path

# ---- gov.il "Shalhevet" API endpoints (reverse-engineered together with the user) ----
TREE_URL_TEMPLATE = "https://www.gov.il/api/kabaut/shalhevet/api/kabaut/he/shalhevet/{track_id}"
REQUIREMENTS_URL_TEMPLATE = "https://www.gov.il/api/kabaut/shalhevet/api/kabaut/he/shalhevet/getRequirmentsByCategoryId/{category_id}"

TRACK_PERMIT = 1   # matches CATEGORY_TYPE_ID 1 -> local group ids 1-99  (בניה/היתר)
TRACK_BUSINESS = 2  # matches CATEGORY_TYPE_ID 2 -> local group ids 100+ (רישוי עסקים)

# Be a polite, slow, single-threaded client. This is an undocumented internal API
# we found by inspecting network traffic, not a published public API - see the
# README for why this matters.
REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    # The API returned 403 Forbidden without these on the first real run - it
    # appears to check that the request looks like it came from inside the
    # actual app page, not from an arbitrary script.
    "Referer": "https://www.gov.il/apps/Kabaut/Shalhevet/treeView/?mainCatId=1",
    "Origin": "https://www.gov.il",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "X-Requested-With": "XMLHttpRequest",
}

# The page the API's own front-end loads before ever calling the API - hitting
# it first (in a shared session) picks up whatever cookies the server expects
# to see on the subsequent API calls, the same way a real browser tab would.
WARMUP_URL = "https://www.gov.il/apps/Kabaut/Shalhevet/treeView/?mainCatId=1"


# ---- Directory layout ----
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"                       # raw API responses, one file per request
TREE_PERMIT_FILE = CACHE_DIR / "tree_permit.json"
TREE_BUSINESS_FILE = CACHE_DIR / "tree_business.json"
REQUIREMENTS_DIR = CACHE_DIR / "requirements"         # one file per fetched leaf category
PROGRESS_FILE = CACHE_DIR / "fetch_progress.json"     # which leaves are already done (resume support)

OUTPUT_DIR = BASE_DIR / "output"
DATA_BLOCK_FILE = OUTPUT_DIR / "data_block.js"        # the rebuilt "const DATA = {...}" block
BUILD_REPORT_FILE = OUTPUT_DIR / "build_report.json"  # stats about the rebuild, for the diff step

# GitHub Pages build: one small JSON file per group instead of one giant DATA
# block - the site fetches only the file for whichever group the person picks,
# instead of holding every group's rows in memory the whole time.
SITE_DIR = OUTPUT_DIR / "site"           # the folder you copy into the GitHub repo
SITE_DATA_DIR = SITE_DIR / "data"        # one group_<g>.json per group, inside it

# The original tool's HTML template and the two script blocks that sit around the
# DATA block (script index 0 = DATA itself, per the original file's <script> order).
HTML_TEMPLATE_FILE = BASE_DIR.parent / "naf_tool_fixed.html"
HTML_OUTPUT_FILE = OUTPUT_DIR / "naf_tool_updated.html"

# GitHub Pages build: the shell page (no data embedded) that 04_inject_html.py
# fills in with GROUPS_INDEX/CHUNK_MANIFEST and writes into the site/ folder
# alongside the per-group data files 03_build_data.py already wrote there.
SITE_TEMPLATE_FILE = BASE_DIR.parent / "site_template.html"
SITE_INDEX_FILE = SITE_DIR / "index.html"


def diagnose_http_error(exc: "requests.RequestException"):
    """Prints whatever the server actually sent back on a failed request - a
    403/blocked response often carries a body or header that names the reason
    (a WAF vendor, a missing-token message, a captcha page...), which saves a
    round trip to DevTools if we can read it directly."""
    response = getattr(exc, "response", None)
    if response is None:
        return
    print(f"    -> status {response.status_code}, {len(response.content)} bytes")
    interesting_headers = {
        k: v for k, v in response.headers.items()
        if k.lower() in {"server", "x-akamai-request-id", "cf-ray", "x-amz-cf-id",
                          "x-cache", "content-type", "set-cookie"}
    }
    if interesting_headers:
        print(f"    -> response headers of interest: {interesting_headers}")
    body_preview = response.text[:500].strip()
    if body_preview:
        print(f"    -> response body (first 500 chars):\n{body_preview}")


def ensure_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)


def create_session() -> "requests.Session":
    """A requests.Session pre-loaded with the warm-up page's cookies, so every
    call site (fetch_trees, fetch_requirements) gets the same treatment a real
    browser tab would: load the app page once, then call the API with the
    session/cookies that page set."""
    import requests  # local import - common.py stays import-light for callers that don't need it

    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(WARMUP_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        print(f"  (warm-up request to {WARMUP_URL} failed - continuing anyway: {exc})")
    return session
