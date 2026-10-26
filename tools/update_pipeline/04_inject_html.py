"""
Stage 4 of 4: build the final GitHub Pages site - index.html plus the
data/group_<g>.json files 03b_build_from_opendata.py already wrote into output/site/.

Unlike the old single-file build, this stage does NOT embed any requirement
data into the page. It only fills in two small, always-loaded pieces of
config: GROUPS_INDEX (every group's id and name, so the picker screen needs
no network call) and CHUNK_MANIFEST (which data/ file each group's own
requirements live in). Everything else in site_template.html - the CSS, the
CALC tables, the wizard/UI logic - is copied through unchanged.

    python3 04_inject_html.py

After this finishes, output/site/ is the complete, ready-to-publish folder:
copy its contents (index.html + data/) into your cloned GitHub repo and
push - see README.md "Publishing an update".
"""
import json

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")   # Hebrew output on Windows consoles
    except Exception: pass
from common import SITE_TEMPLATE_FILE, SITE_DIR, SITE_INDEX_FILE, BUILD_REPORT_FILE, ensure_dirs

PLACEHOLDER = "/*GROUPS_CONFIG_PLACEHOLDER*/"


def main():
    ensure_dirs()

    groups_index_file = SITE_DIR / "groups_index.json"
    if not groups_index_file.exists():
        raise SystemExit("No groups_index.json found - run 03b_build_from_opendata.py first.")
    if not SITE_TEMPLATE_FILE.exists():
        raise SystemExit(f"Site template not found at {SITE_TEMPLATE_FILE}")

    groups_index = json.loads(groups_index_file.read_text(encoding="utf-8"))
    template = SITE_TEMPLATE_FILE.read_text(encoding="utf-8")

    if PLACEHOLDER not in template:
        raise SystemExit(
            f"Could not find the {PLACEHOLDER!r} marker in {SITE_TEMPLATE_FILE} - "
            f"the template may have changed since this script was written."
        )

    updated_at = data_date = None
    if BUILD_REPORT_FILE.exists():
        build_report = json.loads(BUILD_REPORT_FILE.read_text(encoding="utf-8"))
        updated_at, data_date = build_report.get("updatedAt"), build_report.get("dataDate")

    chunk_manifest = {str(g["g"]): f"data/group_{g['g']}.json" for g in groups_index}
    config_block = (
        "const GROUPS_INDEX = " + json.dumps(groups_index, ensure_ascii=False) + ";\n"
        "const CHUNK_MANIFEST = " + json.dumps(chunk_manifest, ensure_ascii=False) + ";\n"
        "const SITE_UPDATED_AT = " + json.dumps(updated_at, ensure_ascii=False) + ";\n"
        "const SITE_DATA_DATE = " + json.dumps(data_date, ensure_ascii=False) + ";"
    )

    final_html = template.replace(PLACEHOLDER, config_block)
    SITE_INDEX_FILE.write_text(final_html, encoding="utf-8")

    print(f"Wrote {SITE_INDEX_FILE} ({len(final_html.encode('utf-8'))/1024:.0f} KB)")
    print(f"{len(groups_index)} groups wired to their data/ files.")
    print(f"Site shows 'last updated: {updated_at}' and 'data as of: {data_date}' in the header.")
    print(f"\nThe complete site is ready at: {SITE_DIR}")
    print("Copy its contents into your cloned GitHub repo folder, then commit + push with GitHub Desktop.")


if __name__ == "__main__":
    main()
