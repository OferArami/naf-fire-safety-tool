"""
Stage 3 of 4: turn the cached tree + per-leaf requirement files into the
GitHub Pages site's data files - one small JSON file per group instead of one
giant DATA block, so the published site only ever downloads the group a
person actually picks (see README.md "Why per-group files").

    python3 03_build_data.py
"""
import json
from datetime import date

from common import (
    TREE_PERMIT_FILE, TREE_BUSINESS_FILE, REQUIREMENTS_DIR,
    SITE_DATA_DIR, BUILD_REPORT_FILE, ensure_dirs,
)
from transform import CategoryTree, build_dataset


def load_cached_requirements(leaf_ids) -> dict:
    requirements_by_leaf = {}
    missing = []
    for leaf_id in leaf_ids:
        f = REQUIREMENTS_DIR / f"{leaf_id}.json"
        if not f.exists():
            missing.append(leaf_id)
            continue
        requirements_by_leaf[leaf_id] = json.loads(f.read_text(encoding="utf-8"))
    if missing:
        raise SystemExit(
            f"{len(missing)} leaves have no cached requirements file "
            f"(e.g. {missing[:5]}) - run 02_fetch_requirements.py to finish fetching first."
        )
    return requirements_by_leaf


def main():
    ensure_dirs()

    if not TREE_PERMIT_FILE.exists() or not TREE_BUSINESS_FILE.exists():
        raise SystemExit("Tree files missing - run 01_fetch_trees.py first.")

    permit_nodes = json.loads(TREE_PERMIT_FILE.read_text(encoding="utf-8"))
    business_nodes = json.loads(TREE_BUSINESS_FILE.read_text(encoding="utf-8"))

    combined_tree = CategoryTree(permit_nodes + business_nodes)
    permit_leaves = CategoryTree(permit_nodes).leaves()
    business_leaves = CategoryTree(business_nodes).leaves()
    all_leaves = sorted(set(permit_leaves) | set(business_leaves))

    print(f"Loading cached requirements for {len(all_leaves)} leaves...")
    requirements_by_leaf = load_cached_requirements(all_leaves)
    total_raw_rows = sum(len(v) for v in requirements_by_leaf.values())
    print(f"  {total_raw_rows} raw requirement rows loaded (pre-dedup).")

    print("Building rows (deduplicating shared-ancestor requirements)...")
    pool, rows = build_dataset(combined_tree, requirements_by_leaf)
    print(f"  {len(rows)} unique rows, {len(pool.pool)} unique strings in the shared pool.")

    print("Splitting into one self-contained file per group...")
    # transform.py's rows use SHORT wire-format keys (g,d,l,n,q,m,s) to keep
    # the shared pool-building step itself compact - but each per-group site
    # file we write here uses the FULL friendly names (gd, levels, num, req,
    # rem, src) that script_3.js's ensureGroupLoaded() expects to fetch, since
    # every file is already small on its own and doesn't need further
    # shortening the way the single-file build did.
    by_group: dict = {}
    for row in rows:
        by_group.setdefault(row["g"], []).append(row)

    from transform import StringPool

    groups_index = []
    updated_at = date.today().isoformat()
    for g, group_rows in sorted(by_group.items()):
        local_pool = StringPool()

        def reintern(old_index):
            return local_pool.intern(None if old_index == -1 else pool.pool[old_index])

        local_rows = []
        for row in group_rows:
            local_rows.append({
                "g": row["g"],
                "gd": reintern(row["d"]),
                "levels": [
                    {"code": reintern(lv["c"]), "desc": reintern(lv["d"])}
                    for lv in row["l"]
                ],
                "num": reintern(row["n"]),
                "req": reintern(row["q"]),
                "rem": reintern(row["m"]),
                "src": reintern(row["s"]),
            })
        site_data = {"pool": local_pool.pool, "rows": local_rows}
        out_file = SITE_DATA_DIR / f"group_{g}.json"
        out_file.write_text(json.dumps(site_data, ensure_ascii=False), encoding="utf-8")
        groups_index.append({"g": g, "gd": pool.pool[group_rows[0]["d"]]})

    groups_index.sort(key=lambda x: x["g"])
    (SITE_DATA_DIR.parent / "groups_index.json").write_text(
        json.dumps(groups_index, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  wrote {len(by_group)} files to {SITE_DATA_DIR}")
    print(f"  wrote {SITE_DATA_DIR.parent / 'groups_index.json'}")

    report = {
        "updatedAt": updated_at,
        "leaves_fetched": len(all_leaves),
        "permit_track_leaves": len(permit_leaves),
        "business_track_leaves": len(business_leaves),
        "raw_requirement_rows": total_raw_rows,
        "unique_rows_after_dedup": len(rows),
        "pool_size": len(pool.pool),
        "distinct_groups": len(by_group),
        "group_numbers": sorted(by_group.keys()),
    }
    BUILD_REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {BUILD_REPORT_FILE}")

    print("\nNext: python3 04_inject_html.py")


if __name__ == "__main__":
    main()
