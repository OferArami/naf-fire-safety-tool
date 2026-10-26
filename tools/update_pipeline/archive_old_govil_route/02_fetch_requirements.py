"""
Stage 2 of 4: fetch the requirements for every leaf category, one request at a
time with a polite delay between requests (this is an internal, undocumented
API - see the README).

Safe to interrupt and re-run: every leaf already saved to cache/requirements/
is skipped, so a Ctrl+C part-way through only costs the time already spent,
not a restart from zero.

    python3 02_fetch_requirements.py
"""
import json
import time

import requests

from common import (
    REQUIREMENTS_URL_TEMPLATE, TREE_PERMIT_FILE, TREE_BUSINESS_FILE,
    REQUIREMENTS_DIR, PROGRESS_FILE,
    REQUEST_TIMEOUT_SECONDS, MAX_RETRIES, RETRY_BACKOFF_SECONDS,
    REQUEST_DELAY_SECONDS, ensure_dirs, create_session, diagnose_http_error,
)
from transform import CategoryTree


def load_progress() -> set:
    if PROGRESS_FILE.exists():
        return set(json.loads(PROGRESS_FILE.read_text(encoding="utf-8")))
    return set()


def save_progress(done: set):
    PROGRESS_FILE.write_text(json.dumps(sorted(done)), encoding="utf-8")


def fetch_requirements(session: requests.Session, leaf_id: int) -> list:
    url = REQUIREMENTS_URL_TEMPLATE.format(category_id=leaf_id)
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            print(f"    attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            diagnose_http_error(exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(
        f"giving up on leaf {leaf_id} after {MAX_RETRIES} attempts.\n\n"
        f"If every attempt above showed 'Just a moment...' / status 403 with a "
        f"cloudflare Server header, this isn't a bug to fix here - gov.il sits "
        f"behind a Cloudflare bot-challenge that a plain HTTP client cannot pass. "
        f"Use browser_console_fetch.js instead (see README.md 'If a plain Python "
        f"request gets blocked'), then 02b_import_browser_export.py to continue "
        f"the pipeline from where this script left off."
    ) from last_error


def main():
    ensure_dirs()

    if not TREE_PERMIT_FILE.exists() or not TREE_BUSINESS_FILE.exists():
        raise SystemExit("Tree files missing - run 01_fetch_trees.py first.")

    permit_tree = CategoryTree(json.loads(TREE_PERMIT_FILE.read_text(encoding="utf-8")))
    business_tree = CategoryTree(json.loads(TREE_BUSINESS_FILE.read_text(encoding="utf-8")))

    leaves = sorted(set(permit_tree.leaves()) | set(business_tree.leaves()))
    print(f"{len(leaves)} leaf categories to fetch "
          f"({len(permit_tree.leaves())} permit + {len(business_tree.leaves())} business).")

    done = load_progress()
    remaining = [leaf_id for leaf_id in leaves if leaf_id not in done]
    print(f"{len(done)} already cached from a previous run, {len(remaining)} left to fetch.")

    if not remaining:
        print("Nothing to do. Next: python3 03_build_data.py")
        return

    estimated_minutes = len(remaining) * REQUEST_DELAY_SECONDS / 60
    print(f"Estimated time at {REQUEST_DELAY_SECONDS}s/request: ~{estimated_minutes:.0f} minutes.\n")

    print("Starting a session (loads the app page first, like a real browser tab)...")
    session = create_session()

    for i, leaf_id in enumerate(remaining, start=1):
        print(f"[{i}/{len(remaining)}] fetching category {leaf_id}...")
        requirements = fetch_requirements(session, leaf_id)
        out_file = REQUIREMENTS_DIR / f"{leaf_id}.json"
        out_file.write_text(json.dumps(requirements, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    {len(requirements)} requirement rows -> {out_file.name}")

        done.add(leaf_id)
        save_progress(done)  # checkpoint after every single leaf, not just at the end
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\nAll {len(leaves)} leaves fetched. Next: python3 03_build_data.py")


if __name__ == "__main__":
    main()
