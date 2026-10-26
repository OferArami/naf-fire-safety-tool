"""
Stage 2, browser edition: gov.il's Cloudflare bot-challenge blocks a plain
Python client (confirmed - see the conversation this pipeline came out of),
so the fetch itself has to run inside a real, human-opened browser tab
instead (browser_console_fetch.js). This script just files the 3 JSON files
that script downloads into the same cache/ layout 02_fetch_requirements.py
would have produced, so 03_build_data.py, 04_inject_html.py and
05_diff_report.py need no changes at all.

Usage:
    1. Open https://www.gov.il/apps/Kabaut/Shalhevet/treeView/?mainCatId=1
    2. Open DevTools (F12) -> Console tab
    3. Paste the contents of browser_console_fetch.js and press Enter
    4. Wait for "Done!" (~15-20 minutes) - 3 files download automatically
    5. Move those 3 files into update_pipeline/browser_export/
    6. python 02b_import_browser_export.py
"""
import json

from common import (
    TREE_PERMIT_FILE, TREE_BUSINESS_FILE, REQUIREMENTS_DIR,
    PROGRESS_FILE, BASE_DIR, ensure_dirs,
)

IMPORT_DIR = BASE_DIR / "browser_export"
TREE_PERMIT_SOURCE = IMPORT_DIR / "tree_permit.json"
TREE_BUSINESS_SOURCE = IMPORT_DIR / "tree_business.json"
REQUIREMENTS_SOURCE = IMPORT_DIR / "requirements_by_leaf.json"


def main():
    ensure_dirs()

    missing = [f for f in (TREE_PERMIT_SOURCE, TREE_BUSINESS_SOURCE, REQUIREMENTS_SOURCE) if not f.exists()]
    if missing:
        names = ", ".join(f.name for f in missing)
        raise SystemExit(
            f"Missing file(s) in {IMPORT_DIR}: {names}\n"
            f"Run browser_console_fetch.js in the browser first, then move its "
            f"3 downloaded files into that folder."
        )

    TREE_PERMIT_FILE.write_text(TREE_PERMIT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    TREE_BUSINESS_FILE.write_text(TREE_BUSINESS_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Copied trees -> {TREE_PERMIT_FILE.name}, {TREE_BUSINESS_FILE.name}")

    requirements_by_leaf = json.loads(REQUIREMENTS_SOURCE.read_text(encoding="utf-8"))

    ok_count, error_leaves = 0, []
    for leaf_id_str, requirements in requirements_by_leaf.items():
        if isinstance(requirements, dict) and "__error__" in requirements:
            error_leaves.append((leaf_id_str, requirements["__error__"]))
            continue
        out_file = REQUIREMENTS_DIR / f"{leaf_id_str}.json"
        out_file.write_text(json.dumps(requirements, ensure_ascii=False), encoding="utf-8")
        ok_count += 1

    done_ids = [int(k) for k in requirements_by_leaf if k not in dict(error_leaves)]
    PROGRESS_FILE.write_text(json.dumps(sorted(done_ids)), encoding="utf-8")

    print(f"Imported {ok_count} leaf requirement files -> {REQUIREMENTS_DIR}")
    if error_leaves:
        print(f"\n{len(error_leaves)} leaves failed inside the browser and need a retry:")
        for leaf_id, err in error_leaves:
            print(f"  - {leaf_id}: {err}")
        print(
            "\nThese are NOT in cache/fetch_progress.json, so re-running "
            "browser_console_fetch.js will retry only these (everything else "
            "is skipped as already done)."
        )
    else:
        print("No failed leaves.")

    print("\nNext: python 03_build_data.py")


if __name__ == "__main__":
    main()
