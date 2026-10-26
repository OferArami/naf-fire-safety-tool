"""
Monthly update in one command (data.gov.il route).

Before running: in the browser, open https://data.gov.il, press F12 -> Console, paste opendata_download.js.
It downloads permit.json, business.json and opendata_meta.json into your Downloads folder.

Then:
    python run_update.py --repo C:\\naf-fire-safety-tool            # build + show what changed (nothing is copied)
    python run_update.py --repo C:\\naf-fire-safety-tool --copy     # same, then copy the new site into the repo

After --copy: open GitHub Desktop, commit with the suggested message, push.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")   # Hebrew output on Windows consoles
    except Exception: pass
from common import BASE_DIR, OPENDATA_DIR, SITE_DATA_DIR, SITE_INDEX_FILE, BUILD_REPORT_FILE

NEEDED = ("permit", "business", "opendata_meta")


def newest(folder: Path, stem: str):
    """Newest '<stem>.json' or browser-renamed copy like '<stem> (1).json' / '<stem>(2).json'."""
    pat = re.compile(rf"^{re.escape(stem)}(\s*\(\d+\))?\.json$", re.I)
    files = [f for f in folder.glob("*.json") if pat.match(f.name)]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def take_from_downloads(downloads: Path):
    found = {k: newest(downloads, k) for k in NEEDED}
    if not all(found.values()):
        missing = [k + ".json" for k, v in found.items() if not v]
        print(f"לא נמצאו בתיקיית ההורדות ({downloads}): {', '.join(missing)} — משתמש במה שכבר יש ב-opendata/")
        return False
    OPENDATA_DIR.mkdir(exist_ok=True)
    for k, f in found.items():
        shutil.copy2(f, OPENDATA_DIR / f"{k}.json")
        print(f"  הועתק: {f.name} -> opendata/{k}.json")
    return True


def check_opendata():
    for k in NEEDED:
        if not (OPENDATA_DIR / f"{k}.json").exists():
            raise SystemExit(f"חסר opendata/{k}.json — הריצו קודם את opendata_download.js בדפדפן (ראו README)")
    meta = json.loads((OPENDATA_DIR / "opendata_meta.json").read_text(encoding="utf-8"))
    for k in ("permit", "business"):
        rows = len(json.loads((OPENDATA_DIR / f"{k}.json").read_text(encoding="utf-8")))
        if rows != meta[k]["rows"]:
            raise SystemExit(f"{k}.json מכיל {rows} שורות אבל המאגר מדווח {meta[k]['rows']} — ההורדה לא הושלמה, הורידו שוב")
        print(f"  {k}: {rows} שורות, {meta[k]['name']}")
    return min(meta[k]["data_date"] for k in ("permit", "business"))


def site_data_date(index_html: Path):
    if not index_html.exists():
        return None
    m = re.search(r'const SITE_DATA_DATE = "([^"]*)"', index_html.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def run(script, *args):
    print(f"\n>>> {script} {' '.join(args)}")
    subprocess.run([sys.executable, str(BASE_DIR / script), *args], check=True, cwd=BASE_DIR,
                   env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})


def copy_into_repo(repo: Path):
    (repo / "data").mkdir(exist_ok=True)
    shutil.copy2(SITE_INDEX_FILE, repo / "index.html")
    new_names = {f.name for f in SITE_DATA_DIR.glob("group_*.json")}
    for f in SITE_DATA_DIR.glob("group_*.json"):
        shutil.copy2(f, repo / "data" / f.name)
    stale = [f for f in (repo / "data").glob("group_*.json") if f.name not in new_names]
    for f in stale:
        f.unlink()
        print(f"  נמחק מה-repo (הקבוצה כבר לא קיימת במאגר): data/{f.name}")
    print(f"  הועתקו index.html ו-{len(new_names)} קבצי data/ אל {repo}")


def main():
    ap = argparse.ArgumentParser(description="עדכון חודשי של נתוני הדרישות")
    ap.add_argument("--repo", required=True, help="תיקיית ה-repo של האתר, למשל C:\\naf-fire-safety-tool")
    ap.add_argument("--downloads", default=str(Path.home() / "Downloads"), help="מאיפה לקחת את הקבצים שהורדו")
    ap.add_argument("--copy", action="store_true", help="להעתיק את האתר החדש לתוך ה-repo")
    ap.add_argument("--force", action="store_true", help="לבנות גם אם הנתונים לא חדשים מהאתר")
    a = ap.parse_args()
    repo = Path(a.repo)
    if not (repo / "index.html").exists():
        raise SystemExit(f"{repo} לא נראית כמו תיקיית האתר (אין בה index.html)")

    print("1) קבצי הנתונים")
    downloads = Path(a.downloads)
    if downloads.exists():
        take_from_downloads(downloads)
    new_date = check_opendata()
    live_date = site_data_date(repo / "index.html")
    print(f"  באתר כרגע: נכון ל-{live_date or '?'} | בקבצים שהורדו: נכון ל-{new_date}")
    if live_date and new_date <= live_date and not a.force:
        print("\nאין נתונים חדשים מאלה שכבר באתר — אין מה לעדכן. (להריץ בכל זאת: --force)")
        return

    print("\n2) בנייה")
    run("03b_build_from_opendata.py")
    run("04_inject_html.py")
    report = json.loads(BUILD_REPORT_FILE.read_text(encoding="utf-8"))
    if report.get("repaired_rows"):
        print(f"  הערה: {len(report['repaired_rows'])} שורות שבורות בקובץ הרשות תוקנו אוטומטית (פירוט ב-output/build_report.json)")

    print("\n3) מה ישתנה")
    run("05_diff_report.py", str(repo))

    if a.copy:
        print("\n4) העתקה ל-repo")
        copy_into_repo(repo)
        print("\nעכשיו: GitHub Desktop -> Commit עם ההודעה:")
        print(f"  Update fire requirements data to {new_date}")
        print("ואז Push origin.")
    else:
        print("\nשום דבר לא הועתק. אם הדוח נראה תקין, הריצו שוב עם --copy")


if __name__ == "__main__":
    main()
