"""
Build the site's data/ files from the Fire Authority's OFFICIAL open-data files on data.gov.il
(the "דרישות בטיחות אש להיתרי בניה" and "דרישות בטיחות אש לרישוי עסקים" datasets).

This replaces the gov.il "Shalhevet" scraping route (blocked by Cloudflare): the open-data files are
public, updated monthly by the Authority, and contain exactly what the tool needs - one row per
requirement, anchored at its category node (so requirements that apply to a whole group / sub-category
appear once at that node, the same way the tool already treats them).

Input  (put in update_pipeline/opendata/):  permit.json, business.json   (see README, "עדכון מ-data.gov.il")
Output (update_pipeline/output/site/):      data/group_<g>.json, groups_index.json   -> then run 04_inject_html.py

    python3 03b_build_from_opendata.py
"""
import json, re, sys
from datetime import date
from pathlib import Path

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")   # Hebrew output on Windows consoles
    except Exception: pass
BASE = Path(__file__).resolve().parent
IN_DIR = BASE / "opendata"
SITE_DIR = BASE / "output" / "site"
DATA_DIR = SITE_DIR / "data"
BUSINESS_OFFSET = 1000          # business groups are offset by 1000 (trackOf(g) in the site relies on it)
MAX_LEVELS = 6                  # the site renders up to 6 sub-levels

def clean(v):
    if v is None: return ""
    if isinstance(v, float):
        v = str(int(v)) if v.is_integer() else repr(v)
    v = str(v).strip()
    return "" if v in ("NULL", "None", "nan") else v

KNOWN_SRC_MAX_LEN = 60
FIELDS = ['CategoryCode1','CategoryDesc1','CategoryCode2','CategoryDesc2','CategoryCode3','CategoryDesc3','CategoryCode4',
          'CategoryDesc4','CategoryCode5','CategoryDesc5','CategoryCode6','CategoryDesc6','CategoryCode7','CategoryDesc7',
          'RequirementNumber','RequirementDesc','Remarks','REQUIREMENT_SOURCE_DESC']

def repair_shifted_row(r):
    """Authority export bug: a category description with a quotation mark swallows the next columns
    ('...ותחת"פ,,,,' or '...הקובעת,_05.01.01,<desc>,,'), every later column shifts right, and the requirement
    text ends up split over CategoryDesc6..RequirementDesc. Undo it: split the swollen description back into
    its fields (separators are commas with no space after them), re-align the rest, and rejoin the requirement
    text from its pieces. Returns (fixed_row, n_fields_recovered) or (None, 0) when the row is not of that shape
    or the result does not look sane."""
    vals = ["" if r.get(f) is None else str(r.get(f)) for f in FIELDS]
    for i, f in enumerate(FIELDS[:14]):
        if not f.startswith("CategoryDesc") or not re.search(r",+\s*$|,_?\d+(\.\d+)+,", vals[i]):
            continue
        swollen = re.sub(r",(_?\d+(?:\.\d+)+),\s+", r",\1,", vals[i])   # a code is always its own field
        pieces = re.split(r"(?<!\d),(?! )|(?<=\d),(?! )(?!\d{3}(?![\d.]))", swollen)
        lst = vals[:i] + pieces + vals[i + 1:]
        extra = len(lst) - len(FIELDS)
        if extra < 1:
            return None, 0
        di = FIELDS.index("RequirementDesc")
        parts = lst[di:di + extra + 1]
        parts[-1] = re.sub(r'"\s*$', "", parts[-1])   # the closing quote of the broken CSV field
        desc = ",".join(parts).replace('""', '"').strip()
        out = dict(r)
        out.update(zip(FIELDS, lst[:di] + [desc] + lst[di + extra + 1:]))
        rem = out["Remarks"].replace('""', '"').strip()
        out["Remarks"] = re.sub(r'\s*"$', "", rem) if rem.count('"') % 2 else rem
        num = out["RequirementNumber"].strip()
        ok = ((num == "" or re.match(r"[_\d]", num)) and len(num) <= 30 and len(out["REQUIREMENT_SOURCE_DESC"].strip()) <= 60
              and all(len(str(out[f"CategoryCode{k}"]).strip()) <= 15 for k in range(1, 8)))
        return (out, len(pieces) - 1) if ok else (None, 0)
    return None, 0


def repair_source(desc, rem, src, notes, ctx):
    """The Authority's export occasionally has broken CSV quoting: a text containing quotation marks is split
    on its commas and the rest spills into the next columns, ending in the source column as
    '..overflow text..",<remark>,<real source>' (spill started in the description) or
    '..overflow text..",<real source>' (spill started in the remarks).
    A real source label is short and has no quotation marks, so detect that shape and put the pieces back."""
    if not src or ('"' not in src and len(src) <= KNOWN_SRC_MAX_LEN):
        return desc, rem, src
    m = re.match(r'(.*)"\s*,(.*)$', src.strip(), re.S)
    if not m:
        notes.append({"row": ctx, "action": "source column looks broken but could not be split - moved it into remarks",
                      "source_now": ""})
        return desc, clean((rem + " " + src.replace('""', '"')).strip()), ""
    overflow = m.group(1).replace('""', '"').strip()
    tail = [t.strip() for t in m.group(2).split(",")]
    real_src = clean(re.sub(r"\s+", " ", tail[-1]))
    if len(tail) >= 2:   # spill started in the description: desc + remarks-column + overflow are one text
        desc = clean(", ".join(x for x in (desc, rem.replace('""', '"'), overflow) if x).replace('""', '"'))
        rem = clean(",".join(tail[:-1]))
        action = "rejoined a description that was split across the remarks and source columns"
    else:                # spill started in the remarks
        rem = clean(", ".join(x for x in (rem.replace('""', '"'), overflow) if x))
        action = "moved overflow text from source column into remarks"
    notes.append({"row": ctx, "action": action, "source_now": real_src})
    return desc, rem, real_src

def group_number(code):
    m = re.match(r"\s*_?(\d+)", clean(code))
    if not m: raise SystemExit(f"group code {code!r} has no number")
    return int(m.group(1))

class Pool:
    def __init__(self): self.idx, self.items = {}, []
    def i(self, v):
        v = clean(v)
        if v == "": return -1
        if v not in self.idx:
            self.idx[v] = len(self.items); self.items.append(v)
        return self.idx[v]

def load(name):
    f = IN_DIR / name
    if not f.exists(): raise SystemExit(f"missing {f} - download it first (see README)")
    return json.loads(f.read_text(encoding="utf-8"))

def main():
    rows_by_group, group_desc = {}, {}
    seen = set()
    repairs = []
    total = 0
    for name, business in (("permit.json", False), ("business.json", True)):
        for r in load(name):
            total += 1
            fixed, n_fields = repair_shifted_row(r)
            if fixed:
                r = fixed
                repairs.append({"row": {"file": name, "_id": r.get("_id"), "num": clean(r.get("RequirementNumber"))},
                                "action": f"re-aligned a row whose category description had swallowed {n_fields} columns",
                                "source_now": clean(r.get("REQUIREMENT_SOURCE_DESC"))})
            g = group_number(r["CategoryCode1"]) + (BUSINESS_OFFSET if business else 0)
            levels = []
            for k in range(2, 8):
                code, desc = clean(r.get(f"CategoryCode{k}")), clean(r.get(f"CategoryDesc{k}"))
                if code == "": break
                levels.append((code, desc))
            if len(levels) > MAX_LEVELS:
                raise SystemExit(f"group {g}: {len(levels)} sub-levels, more than the site supports ({MAX_LEVELS})")
            desc, rem, src = repair_source(clean(r.get("RequirementDesc")), clean(r.get("Remarks")),
                                           clean(r.get("REQUIREMENT_SOURCE_DESC")), repairs,
                                           {"file": name, "_id": r.get("_id"), "num": clean(r.get("RequirementNumber"))})
            row = (g, tuple(levels), clean(r.get("RequirementNumber")), desc, rem, src)
            if row in seen: continue            # exact duplicates carry no information
            seen.add(row)
            rows_by_group.setdefault(g, []).append(row)
            group_desc.setdefault(g, clean(r.get("CategoryDesc1")))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for old in DATA_DIR.glob("group_*.json"): old.unlink()
    index = []
    for g in sorted(rows_by_group):
        p = Pool(); gd = p.i(group_desc[g]); out = []
        for _, levels, num, req, rem, src in rows_by_group[g]:
            out.append({"g": g, "gd": gd,
                        "levels": [{"code": p.i(c), "desc": p.i(d)} for c, d in levels],
                        "num": p.i(num), "req": p.i(req), "rem": p.i(rem), "src": p.i(src)})
        (DATA_DIR / f"group_{g}.json").write_text(json.dumps({"pool": p.items, "rows": out}, ensure_ascii=False), encoding="utf-8")
        index.append({"g": g, "gd": group_desc[g]})
    (SITE_DIR / "groups_index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    meta_file = IN_DIR / "opendata_meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    data_dates = sorted(v.get("data_date", "") for v in meta.values() if v.get("data_date"))
    if not meta:
        print("WARNING: opendata/opendata_meta.json is missing - the site will not show the data date.")
    report = {"updatedAt": date.today().isoformat(), "dataDate": data_dates[0] if data_dates else None,
              "datasets": meta, "source": "data.gov.il open data",
              "raw_rows": total, "unique_rows": sum(len(v) for v in rows_by_group.values()),
              "distinct_groups": len(rows_by_group), "group_numbers": sorted(rows_by_group),
              "repaired_rows": repairs}
    (BASE / "output").mkdir(exist_ok=True)
    (BASE / "output" / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    print("Next: python3 04_inject_html.py")

if __name__ == "__main__":
    main()
