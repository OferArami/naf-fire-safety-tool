"""
Rebuilds the tool's internal DATA structure (pool + rows) from the raw category-tree
and requirements responses fetched from gov.il.

This module intentionally mirrors the exact layout documented at the top of the
original script_3.js:

    DATA = {pool:[strings...], rows:[[g,gd_i,c2_i,d2_i,c3_i,d3_i,c4_i,d4_i,c5_i,d5_i,
                                       num_i,req_i,rem_i,src_i], ...]}
    LEVELS = [[2,3],[4,5],[6,7],[8,9]]   # [codeCol, descCol] pairs, 4 sub-levels max

Column 0 (g) is a small integer parsed from the group's own CATEGORY_CODE
(e.g. "_14" -> 14, "101" -> 101) - NOT the database CATEGORY_ID, which is an
unrelated, non-sequential primary key. Getting this right matters: the wizard's
group list, search box and track split (permit vs business) all key off "g".

Every requirement returned by the API is tagged with a CATEGORY_ID indicating which
node along the root-to-leaf path it is "anchored" to. A requirement anchored at an
ancestor node applies to every leaf beneath it - reproduced here as a "general row"
(-1 in every level column deeper than the anchor), exactly matching how
activeRows() in the wizard already treats -1 as "matches any choice at this level".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

MAX_SUB_LEVELS = 6          # some business-license categories nest this deep (confirmed against the real dataset)


# --------------------------------------------------------------------------- #
# Category tree
# --------------------------------------------------------------------------- #

@dataclass
class CategoryNode:
    category_id: int
    parent_id: int
    code: str
    desc: str
    category_type_id: int
    children: List[int] = field(default_factory=list)


class CategoryTree:
    """Indexes the flat list of category rows returned by the tree endpoints,
    and answers the two questions the row-builder needs: 'what is this node's
    full path to the root?' and 'which nodes have no children (are leaves)?'."""

    def __init__(self, raw_nodes: List[dict]):
        self.nodes: Dict[int, CategoryNode] = {}
        for n in raw_nodes:
            cid = n["CATEGORY_ID"]
            self.nodes[cid] = CategoryNode(
                category_id=cid,
                parent_id=n["PARENT_CATEGORY_ID"],
                code=(n["CATEGORY_CODE"] or "").strip(),
                desc=(n["CATEGORY_DESC"] or "").strip(),
                category_type_id=n["CATEGORY_TYPE_ID"],
            )
        for node in self.nodes.values():
            parent = self.nodes.get(node.parent_id)
            if parent is not None:
                parent.children.append(node.category_id)

    def leaves(self) -> List[int]:
        """Category ids with no children - the terminal nodes of the tree."""
        return [cid for cid, n in self.nodes.items() if not n.children]

    def path_to_root(self, category_id: int) -> List[CategoryNode]:
        """Root-first ordered path, e.g. [group, level0, level1, ...]."""
        chain: List[CategoryNode] = []
        cid = category_id
        seen = set()
        while cid in self.nodes and cid not in seen:
            seen.add(cid)
            node = self.nodes[cid]
            chain.append(node)
            if node.parent_id == 0:
                break
            cid = node.parent_id
        chain.reverse()
        return chain

    def group_number(self, category_id: int) -> int:
        """The small integer used throughout the wizard as 'g' (column 0),
        parsed from the top-level ancestor's own CATEGORY_CODE and offset by
        track (CATEGORY_TYPE_ID) so permit and business groups never collide -
        see offset_group_number() for why this is needed."""
        path = self.path_to_root(category_id)
        if not path:
            raise ValueError(f"category {category_id} not found in tree")
        group_node = path[0]
        raw_number = parse_group_number(group_node.code)
        return offset_group_number(raw_number, group_node.category_type_id)


def parse_group_number(code: str) -> int:
    """'_14' -> 14, '101' -> 101, ' _01' -> 1, '_33.01' -> 33 (NOT 3301 - only the
    digits before the first separator count; a dotted code at the *group* level
    means "variant of the same group", not "nested sub-level", e.g. both
    '_33.01' תחנת רכבת and '_33.02' תחנת רכבת-תוספת בנייה are group 33).
    Raises if the code has no leading digits at all, since that would silently
    corrupt the group split."""
    match = re.match(r"\s*_?(\d+)", code)
    if not match:
        raise ValueError(f"category code {code!r} has no leading digits to parse a group number from")
    return int(match.group(1))


# Track-1 (permit) group numbers, as they exist in the fresh data, span both the
# legacy scheme ('_01'..'_46' -> 1-46) and the 2023-amendment scheme
# ('100'..'143' -> 100-143) - both are CATEGORY_TYPE_ID 1. Track-2 (business)
# groups are numbered '01'..'10' with NO offset of their own in the source data,
# which collides head-on with track-1's legacy 1-46 range once the leading
# zero/underscore is stripped. BUSINESS_TRACK_OFFSET pushes every business group
# number well clear of every permit-track number (max observed permit number is
# 143), so a single "g" integer stays a reliable, collision-free key across both
# tracks - matching the assumption the wizard's own trackOf(g) makes.
BUSINESS_TRACK_OFFSET = 1000


def offset_group_number(raw_group_number: int, category_type_id: int) -> int:
    if category_type_id == 2:
        return raw_group_number + BUSINESS_TRACK_OFFSET
    return raw_group_number


# --------------------------------------------------------------------------- #
# String pool
# --------------------------------------------------------------------------- #

class StringPool:
    """Interns strings into a flat list, same as the original tool's DATA.pool.
    Empty/whitespace-only strings are treated as absent (-1), matching how the
    wizard's own `s()` helper already collapses null and '' to the same falsy
    value wherever it is read (e.g. the 'מקור לא צוין' fallback)."""

    def __init__(self):
        self._index: Dict[str, int] = {}
        self._pool: List[str] = []

    def intern(self, value: Optional[str]) -> int:
        if value is None:
            return -1
        value = value.strip()
        if value == "":
            return -1
        if value not in self._index:
            self._index[value] = len(self._pool)
            self._pool.append(value)
        return self._index[value]

    @property
    def pool(self) -> List[str]:
        return self._pool


# --------------------------------------------------------------------------- #
# Row building
# --------------------------------------------------------------------------- #

def build_row(
    tree: CategoryTree,
    pool: StringPool,
    leaf_id: int,
    requirement: dict,
) -> Tuple[int, dict]:
    """Builds one requirement row, anchored at whichever category in the
    leaf's path the API tagged it with.

    The row is a dict, but with SHORT wire-format keys - {g, d, l, n, q, m, s} -
    not the friendly names the rest of the app uses (g, gd, levels, num, req,
    rem, src). This keeps the shipped file small (repeated 60,000+ times,
    every extra character in a key name adds up), while script_3.js expands
    every row back to the friendly names in one pass immediately after DATA
    loads, so every consumption site elsewhere in the app is unaffected and
    keeps reading `row.req`, `row.levels[i].code`, etc exactly as before -
    only this function and that one expansion step know about the short keys.

    `l` (levels) holds exactly as many entries as the anchor's own depth (0 to
    MAX_SUB_LEVELS) - a level beyond that length is implicitly "matches any
    choice here", replacing the old -1 sentinel with the array simply ending.
    This is the key structural fix over the old flat-array-of-14/18-fixed-
    columns format: adding a deeper level, or a second numbering scheme that
    needs its own offset, can no longer silently collide with an unrelated
    field the way positional indices did (see the group-offset and
    LEVELS-depth bugs this replaced).

    Returns (dedup_key_requirement_id, row) where the caller is expected to
    dedupe on (anchor_category_id, requirement_id) - see build_dataset().
    """
    anchor_id = requirement["CATEGORY_ID"]
    path = tree.path_to_root(leaf_id)
    path_ids = [n.category_id for n in path]

    if anchor_id not in path_ids:
        # Defensive: every requirement returned for a leaf should be anchored
        # somewhere on that leaf's own root-to-leaf path. If it isn't, the
        # tree we fetched and the requirements response disagree - surface
        # this loudly rather than silently mis-filing the row.
        raise ValueError(
            f"requirement {requirement.get('REQUIREMENT_ID')} anchored at "
            f"category {anchor_id}, which is not on the path to leaf {leaf_id}"
        )

    anchor_depth = path_ids.index(anchor_id)  # 0 = the group itself
    group_node = path[0]
    g = offset_group_number(parse_group_number(group_node.code), group_node.category_type_id)
    gd_i = pool.intern(group_node.desc)

    sub_levels = path[1:]  # everything below the group, up to MAX_SUB_LEVELS deep
    if len(sub_levels) > MAX_SUB_LEVELS:
        raise ValueError(
            f"category {leaf_id} is {len(sub_levels)} sub-levels deep, "
            f"more than the {MAX_SUB_LEVELS} the wizard currently supports - "
            f"the source data has grown a level deeper than the tool can render."
        )

    # levels only goes as deep as the anchor itself - nothing beyond it is
    # appended, which IS the "applies to any choice below this point" marker.
    levels = [
        {"c": pool.intern(node.code), "d": pool.intern(node.desc)}
        for node in sub_levels[:anchor_depth]
    ]

    row = {
        "g": g,
        "d": gd_i,
        "l": levels,
        "n": pool.intern(requirement.get("REQUIREMENT_NUMBER")),
        "q": pool.intern(requirement.get("REQUIREMENT_DESC")),
        "m": pool.intern(requirement.get("REQUIREMENT_REMARKS")),
        "s": pool.intern(requirement.get("REQUIREMENT_SOURCE_DESC")),
    }

    return requirement.get("REQUIREMENT_ID"), row


def build_dataset(
    tree: CategoryTree,
    requirements_by_leaf: Dict[int, List[dict]],
) -> Tuple[StringPool, List[dict]]:
    """Turns {leaf_id: [requirement, ...]} into a deduplicated (pool, rows) pair.

    A requirement anchored at a shared ancestor is returned once per leaf beneath
    it, so it is deduplicated here on (anchor_category_id, REQUIREMENT_ID) - the
    same key that makes it a single logical row in the original tool.
    """
    pool = StringPool()
    rows: List[dict] = []
    seen: set[Tuple[int, int]] = set()

    for leaf_id, requirements in requirements_by_leaf.items():
        for req in requirements:
            anchor_id = req["CATEGORY_ID"]
            req_id = req.get("REQUIREMENT_ID")
            key = (anchor_id, req_id)
            if key in seen:
                continue
            seen.add(key)
            _, row = build_row(tree, pool, leaf_id, req)
            rows.append(row)

    return pool, rows
