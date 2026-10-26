"""
Stage 1 of 4: fetch the two category trees from gov.il and cache them locally.

Run this first - every later stage reads from the cache, never from the network
directly, so a slow/flaky connection only costs you a re-run of this one step.

    python3 01_fetch_trees.py
"""
import json
import time

import requests

from common import (
    TREE_URL_TEMPLATE, TRACK_PERMIT, TRACK_BUSINESS,
    TREE_PERMIT_FILE, TREE_BUSINESS_FILE,
    REQUEST_TIMEOUT_SECONDS, MAX_RETRIES, RETRY_BACKOFF_SECONDS,
    REQUEST_DELAY_SECONDS, ensure_dirs, create_session, diagnose_http_error,
)


def fetch_json(session: requests.Session, url: str) -> list:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            print(f"  attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            diagnose_http_error(exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(
        f"giving up on {url} after {MAX_RETRIES} attempts.\n\n"
        f"If every attempt above showed 'Just a moment...' / status 403 with a "
        f"cloudflare Server header, this isn't a bug to fix here - gov.il sits "
        f"behind a Cloudflare bot-challenge that a plain HTTP client cannot pass. "
        f"Use browser_console_fetch.js instead (see README.md 'If a plain Python "
        f"request gets blocked'), then 02b_import_browser_export.py to continue "
        f"the pipeline from where this script left off."
    ) from last_error


def main():
    ensure_dirs()
    print("Starting a session (loads the app page first, like a real browser tab)...")
    session = create_session()

    print(f"Fetching permit-track tree (track {TRACK_PERMIT})...")
    permit_tree = fetch_json(session, TREE_URL_TEMPLATE.format(track_id=TRACK_PERMIT))
    TREE_PERMIT_FILE.write_text(json.dumps(permit_tree, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  saved {len(permit_tree)} categories -> {TREE_PERMIT_FILE}")

    time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Fetching business-track tree (track {TRACK_BUSINESS})...")
    business_tree = fetch_json(session, TREE_URL_TEMPLATE.format(track_id=TRACK_BUSINESS))
    TREE_BUSINESS_FILE.write_text(json.dumps(business_tree, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  saved {len(business_tree)} categories -> {TREE_BUSINESS_FILE}")

    print("\nDone. Next: python3 02_fetch_requirements.py")


if __name__ == "__main__":
    main()
