"""
Stage 5: show what changed between the site that is published now and the new build.

Compares the data/ folder of the GitHub repo (what is live) with output/site/data/ (the new build)
and writes a readable report to output/diff_report.txt.

    python 05_diff_report.py C:\\naf-fire-safety-tool

A requirement is identified by (group, chosen category codes, requirement number). Rows are compared on
their text, remarks and source. Row identity does not depend on the pool indexes inside the JSON files,
so two separate builds can be compared.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")   # Hebrew output on Windows consoles
    except Exception: pass
from common import SITE_DATA_DIR, SITE_INDEX_FILE, DIFF_REPORT_FILE, OUTPUT_DIR


def norm_code(code: str) -> str:
    """'_01.03.02' and '1.3.2' are the same category; the Authority changes the zero padding between months."""
    return ".".join(part.lstrip("0") or "0" for part in code.strip().lstrip("_").split("."))


def load_rows(data_dir: Path):
    """{group: Counter of (levels_codes, num, req, rem, src)} plus {group: group description}."""
    rows, names = {}, {}
    for f in sorted(data_dir.glob("group_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pool = d["pool"]
        s = lambda i: pool[i] if i is not None and i >= 0 else ""
        c = Counter()
        for r in d["rows"]:
            codes = tuple(norm_code(s(l["code"])) for l in r["levels"])
            c[(codes, s(r["num"]).strip(), s(r["req"]), s(r["rem"]), s(r["src"]))] += 1
            names[r["g"]] = s(r["gd"])
        g = int(f.stem.split("_")[1])
        rows[g] = c
    return rows, names


def data_date_of(index_html: Path):
    if not index_html.exists():
        return None
    import re
    m = re.search(r'const SITE_DATA_DATE = "([^"]*)"', index_html.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def diff(old_dir: Path, new_dir: Path):
    old, old_names = load_rows(old_dir)
    new, new_names = load_rows(new_dir)
    lines, totals = [], Counter()
    for g in sorted(set(old) | set(new)):
        o, n = old.get(g, Counter()), new.get(g, Counter())
        added, removed = n - o, o - n
        # pair an added and a removed row with the same (codes, number) as a text change
        rem_by_key = {}
        for k in removed:
            rem_by_key.setdefault(k[:2], []).append(k)
        changed, pure_added = [], []
        for k in added:
            if rem_by_key.get(k[:2]):
                changed.append((rem_by_key[k[:2]].pop(), k))
            else:
                pure_added.append(k)
        pure_removed = [k for ks in rem_by_key.values() for k in ks]
        if not (changed or pure_added or pure_removed):
            continue
        name = new_names.get(g) or old_names.get(g) or ""
        if g not in old:
            lines.append(f"\n=== קבוצה {g} — {name} — חדשה ({sum(n.values())} שורות)")
        elif g not in new:
            lines.append(f"\n=== קבוצה {g} — {name} — הוסרה")
        else:
            lines.append(f"\n=== קבוצה {g} — {name}: +{len(pure_added)} נוספו, -{len(pure_removed)} הוסרו, ~{len(changed)} שונו")
        # the same requirement often sits in several sub-categories: list it once with a count
        for sign, keys in (("+", pure_added), ("-", pure_removed)):
            for (num, req), cnt in Counter((k[1], k[2]) for k in keys).items():
                lines.append(f"  {sign} [{num}] {req[:160]}" + (f"  (ב-{cnt} תתי-קטגוריות)" if cnt > 1 else ""))
        for a, b in changed:
            what = [w for w, i in (("נוסח", 2), ("הערה", 3), ("מקור", 4)) if a[i] != b[i]]
            lines.append(f"  ~ [{b[1]}] השתנה: {', '.join(what)} — {b[2][:120]}")
        totals["added"] += len(pure_added); totals["removed"] += len(pure_removed); totals["changed"] += len(changed)
        totals["groups"] += 1
    return lines, totals


def main():
    if len(sys.argv) < 2:
        raise SystemExit("שימוש: python 05_diff_report.py <תיקיית ה-repo, למשל C:\\naf-fire-safety-tool>")
    repo = Path(sys.argv[1])
    old_dir, new_dir = repo / "data", SITE_DATA_DIR
    for d in (old_dir, new_dir):
        if not d.exists():
            raise SystemExit(f"לא נמצאה התיקייה {d}")
    lines, t = diff(old_dir, new_dir)
    head = [
        "דוח שינויים — מה ישתנה באתר אחרי העדכון",
        f"נתונים באתר כרגע: נכון ל-{data_date_of(repo / 'index.html') or '?'}",
        f"נתונים בבנייה החדשה: נכון ל-{data_date_of(SITE_INDEX_FILE) or '?'}",
        f"סה\"כ: {t['added']} דרישות נוספו, {t['removed']} הוסרו, {t['changed']} שונו, ב-{t['groups']} קבוצות",
    ]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DIFF_REPORT_FILE.write_text("\n".join(head + lines) + "\n", encoding="utf-8")
    print("\n".join(head))
    print(f"הדוח המלא: {DIFF_REPORT_FILE}")
    return t


if __name__ == "__main__":
    main()
