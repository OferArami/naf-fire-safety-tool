"""
Sanity-checks transform.py against the real API responses the user captured
by hand from DevTools. Run directly: `python3 test_transform.py`.
Not a formal test suite (no pytest) - just a readable, standalone check that
prints exactly what it verified, since the real API can't be reached from here.
"""
import json
from pathlib import Path

from transform import (
    CategoryTree, StringPool, build_row, build_dataset,
    parse_group_number, offset_group_number, BUSINESS_TRACK_OFFSET,
)

SAMPLES = Path(__file__).parent / "samples"


def s(pool_list, i):
    return None if i == -1 else pool_list[i]


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(f"Stopping: {label} failed")


def main():
    tree_nodes = json.loads((SAMPLES / "tree_permit_sample.json").read_text(encoding="utf-8"))
    requirements = json.loads((SAMPLES / "requirements_1752_sample.json").read_text(encoding="utf-8"))

    tree = CategoryTree(tree_nodes)

    print("=== 1. group number parsing ===")
    check("'_01' -> 1", parse_group_number("_01") == 1)
    check("'_14' -> 14", parse_group_number("_14") == 14)
    check("'101' -> 101 (business track, no underscore)", parse_group_number("101") == 101)
    check("'_33.01' -> 33, NOT 3301 (dotted top-level code = variant, not nesting)", parse_group_number("_33.01") == 33)

    print("\n=== 1b. track-collision fix: business and permit groups sharing a raw number don't collide ===")
    check("permit-track raw 1 stays 1 (CATEGORY_TYPE_ID=1)", offset_group_number(1, 1) == 1)
    check(
        f"business-track raw 1 becomes {BUSINESS_TRACK_OFFSET + 1} (CATEGORY_TYPE_ID=2) - no longer collides with permit's g=1",
        offset_group_number(1, 2) == BUSINESS_TRACK_OFFSET + 1,
    )
    check(
        "the 2023-amendment permit group 101 (still CATEGORY_TYPE_ID=1) stays well below the business offset",
        offset_group_number(101, 1) < BUSINESS_TRACK_OFFSET,
    )

    print("\n=== 2. path_to_root for leaf 1752 ===")
    path = tree.path_to_root(1752)
    codes = [n.code for n in path]
    check("path is [_01, _01.03, _01.03.01]", codes == ["_01", "_01.03", "_01.03.01"])
    check("group_number(1752) == 1", tree.group_number(1752) == 1)

    print("\n=== 3. path_to_root for a 5-node-deep leaf (1987) ===")
    deep_path = tree.path_to_root(1987)
    deep_codes = [n.code for n in deep_path]
    check(
        "5-node path (group + 4 sub-levels) resolves without error",
        deep_codes == ["_14", "_14.05", "_14.05.03", "_14.05.03.01", "_14.05.03.01.01"],
    )

    print("\n=== 4. leaves() finds only childless nodes ===")
    leaf_ids = set(tree.leaves())
    check("1752 is a leaf", 1752 in leaf_ids)
    check("2 (has children 1752/1753/2035) is NOT a leaf", 2 not in leaf_ids)
    check("1987 (deepest node in sample) is a leaf", 1987 in leaf_ids)

    print("\n=== 5. build_row: requirement anchored at the ROOT (general row) ===")
    print("    (note: dict keys are the SHORT wire-format keys - g/d/l/n/q/m/s -")
    print("     script_3.js expands these to g/gd/levels/num/req/rem/src at load time)")
    pool = StringPool()
    req_root = next(r for r in requirements if r["REQUIREMENT_ID"] == 204)
    req_id, row = build_row(tree, pool, 1752, req_root)
    check("g == 1", row["g"] == 1)
    check("d (gd) resolves to 'קבוצה 1-מגורים'", s(pool.pool, row["d"]).strip() == "קבוצה 1-מגורים")
    check(
        "l (levels) is EMPTY (root-anchored -> applies to ANY sub-choice, no need for -1 padding)",
        row["l"] == [],
    )
    check("q (req) requirement text matches", s(pool.pool, row["q"]) == "מנעול בדלת בדרך המוצא")

    print("\n=== 6. build_row: requirement anchored at the MIDDLE node (2) ===")
    pool2 = StringPool()
    req_mid = next(r for r in requirements if r["REQUIREMENT_ID"] == 1)
    _, row_mid = build_row(tree, pool2, 1752, req_mid)
    check("l has exactly 1 entry (only as deep as the anchor, no trailing padding)", len(row_mid["l"]) == 1)
    check("l[0].c (code) resolves to '_01.03'", s(pool2.pool, row_mid["l"][0]["c"]) == "_01.03")
    check("l[0].d (desc) resolves to the '13 מ' category name", "13 מ" in s(pool2.pool, row_mid["l"][0]["d"]))

    print("\n=== 7. build_row: requirement anchored at the LEAF itself (1752) ===")
    pool3 = StringPool()
    req_leaf = next(r for r in requirements if r["REQUIREMENT_ID"] == 153)
    _, row_leaf = build_row(tree, pool3, 1752, req_leaf)
    check("l has exactly 2 entries (group -> level0 -> level1 = the leaf itself)", len(row_leaf["l"]) == 2)
    check("l[0].c filled in", s(pool3.pool, row_leaf["l"][0]["c"]) == "_01.03")
    check("l[1].c filled in with the leaf's own code", s(pool3.pool, row_leaf["l"][1]["c"]) == "_01.03.01")
    check("n (num) requirement number preserved", s(pool3.pool, row_leaf["n"]) == "03.04.06.04")
    check("s (src) source preserved", s(pool3.pool, row_leaf["s"]) == "הוראת נציב 550")

    print("\n=== 8. build_row: requirement with empty REQUIREMENT_REMARKS ===")
    req_empty_remarks = next(r for r in requirements if r["REQUIREMENT_ID"] == 375)
    check("REQUIREMENT_REMARKS is '' in the source", req_empty_remarks["REQUIREMENT_REMARKS"] == "")
    pool4 = StringPool()
    _, row_er = build_row(tree, pool4, 1752, req_empty_remarks)
    check("m (rem) empty remarks collapse to -1, not an empty pool entry", row_er["m"] == -1)

    print("\n=== 9. build_dataset: end-to-end dedup across the whole fixture ===")
    pool5, rows = build_dataset(tree, {1752: requirements})
    check("4 requirements in -> 4 rows out (no accidental dedup within one leaf)", len(rows) == 4)
    check("every row is a dict with the expected SHORT keys", all(set(r.keys()) == {"g", "d", "l", "n", "q", "m", "s"} for r in rows))

    # Simulate a second leaf (1753) sharing the same root-anchored requirement (204)
    # to prove the ancestor-level dedup actually kicks in across leaves.
    requirements_leaf_1753 = [dict(req_root, CATEGORY_ID=1)]  # same anchor+id as before
    pool6, rows6 = build_dataset(tree, {1752: requirements, 1753: requirements_leaf_1753})
    check(
        "shared root-anchored requirement (204) is NOT duplicated across two leaves",
        len(rows6) == 4,  # still 4: the 5th input row is a dedup of an existing one
    )

    print("\n=== 10. depth-6 sanity: a deep leaf builds without truncation ===")
    pool7 = StringPool()
    req_deep = {
        "CATEGORY_ID": 1987, "REQUIREMENT_ID": 9001, "REQUIREMENT_NUMBER": "9.9.9",
        "REQUIREMENT_DESC": "דרישה לבדיקת עומק", "REQUIREMENT_REMARKS": "", "REQUIREMENT_SOURCE_DESC": "",
    }
    _, row_deep = build_row(tree, pool7, 1987, req_deep)
    check("l has exactly 4 entries for this fixture's deepest leaf (group + 4 sub-levels)", len(row_deep["l"]) == 4)

    print("\nAll checks passed. The transform matches the real API responses.")


if __name__ == "__main__":
    main()
