"""
Stage 5 (optional): before shipping the rebuilt tool, see exactly what changed
since the last update - new requirements, removed ones, and edited text/remarks/
source on existing ones.

Row identity is defined independently of pool-index numbers (which are
meaningless across two separate builds) as the *resolved* tuple
(group, up to 6 level codes, requirement number) - the same tuple a person
would use to describe "which requirement is this".

    python3 05_diff_report.py
"""
import json
import re
from typing import Dict, List, Tuple

from common import DATA_BLOCK_FILE, HTML_TEMPLATE_FILE, OUTPUT_DIR

DIFF_REPORT_FILE = OUTPUT_DIR / "diff_report.txt"

RowKey = Tuple[int, str, str, str, str, str, str, str]
MAX_LEVELS_IN_KEY = 6


def extract_data_from_html(html_path) -> dict:
    html = html_path.read_text(encoding="utf-8")
    match = re.search(r"<script[^>]*>\s*const DATA = (\{.*?\});", html, re.DOTALL)
    if not match:
        raise SystemExit(f"Could not find a 'const DATA = {{...}};' block in {html_path}")
    return json.loads(match.group(1))


def extract_data_from_block_file(block_path) -> dict:
    text = block_path.read_text(encoding="utf-8").strip()
    prefix, suffix = "const DATA = ", ";"
    if not text.startswith(prefix) or not text.endswith(suffix):
        raise SystemExit(f"{block_path} is not in the expected 'const DATA = {{...}};' shape")
    return json.loads(text[len(prefix):-len(suffix)])


def resolve(pool: List[str], i: int) -> str:
    return "" if i == -1 else pool[i]


def index_rows(data: dict) -> Dict[RowKey, dict]:
    pool = data["pool"]
    index: Dict[RowKey, dict] = {}
    for row in data["rows"]:
        level_codes = tuple(resolve(pool, lvl["code"]) for lvl in row["levels"])
        padded = level_codes + ("",) * (MAX_LEVELS_IN_KEY - len(level_codes))
        key: RowKey = (row["g"], *padded, resolve(pool, row["num"]))
        index[key] = {
            "requirement": resolve(pool, row["req"]),
            "remarks": resolve(pool, row["rem"]),
            "source": resolve(pool, row["src"]),
        }
    return index


def format_key(key: RowKey) -> str:
    g, *level_codes, number = key
    path = " > ".join(c for c in level_codes if c) or "(כללי)"
    return f"קבוצה {g} | {path} | סעיף {number}"


def main():
    if not DATA_BLOCK_FILE.exists():
        raise SystemExit("No rebuilt DATA block found - run 03_build_data.py first.")
    if not HTML_TEMPLATE_FILE.exists():
        raise SystemExit(f"Current tool not found at {HTML_TEMPLATE_FILE}")

    old_data = extract_data_from_html(HTML_TEMPLATE_FILE)
    new_data = extract_data_from_block_file(DATA_BLOCK_FILE)

    old_index = index_rows(old_data)
    new_index = index_rows(new_data)

    added = sorted(set(new_index) - set(old_index), key=format_key)
    removed = sorted(set(old_index) - set(new_index), key=format_key)
    shared = set(old_index) & set(new_index)
    changed = sorted(
        (k for k in shared if old_index[k] != new_index[k]),
        key=format_key,
    )

    lines = []
    lines.append(f"Old dataset: {len(old_data['rows'])} rows, {len(old_data['pool'])} pool strings")
    lines.append(f"New dataset: {len(new_data['rows'])} rows, {len(new_data['pool'])} pool strings")
    lines.append("")
    lines.append(f"Added requirements:   {len(added)}")
    lines.append(f"Removed requirements: {len(removed)}")
    lines.append(f"Changed requirements: {len(changed)}")
    lines.append(f"Unchanged:            {len(shared) - len(changed)}")
    lines.append("")

    if added:
        lines.append(f"=== ADDED ({len(added)}) ===")
        for key in added:
            lines.append(f"  + {format_key(key)}")
            lines.append(f"      {new_index[key]['requirement'][:120]}")
        lines.append("")

    if removed:
        lines.append(f"=== REMOVED ({len(removed)}) ===")
        for key in removed:
            lines.append(f"  - {format_key(key)}")
            lines.append(f"      {old_index[key]['requirement'][:120]}")
        lines.append("")

    if changed:
        lines.append(f"=== CHANGED ({len(changed)}) ===")
        for key in changed:
            lines.append(f"  ~ {format_key(key)}")
            for field in ("requirement", "remarks", "source"):
                old_v, new_v = old_index[key][field], new_index[key][field]
                if old_v != new_v:
                    lines.append(f"      {field}:")
                    lines.append(f"        was: {old_v[:150]}")
                    lines.append(f"        now: {new_v[:150]}")
        lines.append("")

    report = "\n".join(lines)
    DIFF_REPORT_FILE.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n(also written to {DIFF_REPORT_FILE})")


if __name__ == "__main__":
    main()
