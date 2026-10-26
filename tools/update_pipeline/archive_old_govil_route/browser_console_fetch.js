/*
 * מריצים את זה ישירות בתוך DevTools Console, כשהעמוד
 * https://www.gov.il/apps/Kabaut/Shalhevet/treeView/?mainCatId=1
 * פתוח בלשונית (בדיוק אותו עמוד שכבר עבד לך ידנית).
 *
 * למה זה עובד בלי לעקוף שום דבר: הבקשות רצות מתוך ה-JS של העמוד עצמו
 * (same-origin fetch), עם אותם עוגיות/סשן שכבר "אישרו" את הדפדפן שלך
 * מול Cloudflare ברגע שפתחת את העמוד - זה בדיוק אותו מנגנון שהעמוד
 * עצמו משתמש בו כשלוחצים על השאלון בפועל.
 *
 * מה זה עושה:
 *  1. מושך את שני עצי הקטגוריות.
 *  2. מחשב אילו קטגוריות הן "עלים".
 *  3. מושך דרישות לכל עלה, עם השהיה של שנייה בין בקשה לבקשה.
 *  4. שומר התקדמות ל-IndexedDB (לא localStorage - זה חרג ממכסת הכמה-MB שלו
 *     על מאגר בגודל הזה; IndexedDB בנוי בדיוק בשביל נפחים כאלה). אם מרעננים/
 *     סוגרים בטעות - מריצים שוב ומקבלים "resume" אוטומטי, לא מתחילים מאפס.
 *  5. בסוף מוריד 3 קבצי JSON (tree_permit, tree_business, requirements_by_leaf)
 *     - בדיוק מה שהסקריפטים בפייתון (01/02) היו אמורים להוריד בעצמם.
 *
 * משך משוער: 15-20 דקות. אפשר להשאיר את הלשונית פתוחה ברקע ולחזור מאוחר יותר -
 * רק אל תסגרו אותה עד שרואים "Done!" בקונסול.
 */
(async function () {
  const BASE = "https://www.gov.il/api/kabaut/shalhevet/api/kabaut/he/shalhevet";
  const DELAY_MS = 1000;
  const DB_NAME = "shalhevet_fetch_progress_v2";
  const STORE_NAME = "leaves";

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function fetchJson(url) {
    const res = await fetch(url, { credentials: "include" });
    if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
    return res.json();
  }

  function computeLeaves(tree) {
    const parentIds = new Set(tree.map((n) => n.PARENT_CATEGORY_ID));
    return tree.filter((n) => !parentIds.has(n.CATEGORY_ID)).map((n) => n.CATEGORY_ID);
  }

  function downloadJson(filename, data) {
    const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // ---- tiny Promise wrapper around IndexedDB, just the 4 operations we need ----
  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE_NAME);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  function idbPut(db, key, value) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }
  function idbGetAllEntries(db) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const store = tx.objectStore(STORE_NAME);
      const keysReq = store.getAllKeys();
      const valuesReq = store.getAll();
      tx.oncomplete = () => {
        const entries = {};
        keysReq.result.forEach((key, i) => { entries[key] = valuesReq.result[i]; });
        resolve(entries);
      };
      tx.onerror = () => reject(tx.error);
    });
  }
  function idbClear(db) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  console.log("Fetching the two category trees...");
  const treePermit = await fetchJson(`${BASE}/1`);
  const treeBusiness = await fetchJson(`${BASE}/2`);
  console.log(`  permit track: ${treePermit.length} categories`);
  console.log(`  business track: ${treeBusiness.length} categories`);
  downloadJson("tree_permit.json", treePermit);
  downloadJson("tree_business.json", treeBusiness);

  const leaves = [...new Set([...computeLeaves(treePermit), ...computeLeaves(treeBusiness)])];
  console.log(`${leaves.length} leaf categories to fetch requirements for.`);

  const db = await openDb();
  let results = await idbGetAllEntries(db);
  const alreadyDone = Object.keys(results).length;
  if (alreadyDone > 0) {
    console.log(`Resuming: ${alreadyDone} leaves already fetched in a previous run.`);
  }

  const remaining = leaves.filter((id) => !(id in results) || results[id].__error__);
  const estimatedMinutes = Math.ceil((remaining.length * DELAY_MS) / 60000);
  console.log(`${remaining.length} left to fetch, ~${estimatedMinutes} minutes estimated.`);

  for (let i = 0; i < remaining.length; i++) {
    const leafId = remaining[i];
    console.log(`[${i + 1}/${remaining.length}] fetching category ${leafId}...`);
    let value;
    try {
      value = await fetchJson(`${BASE}/getRequirmentsByCategoryId/${leafId}`);
    } catch (err) {
      console.error(`  failed on ${leafId}:`, err);
      value = { __error__: String(err) };
    }
    results[leafId] = value;
    await idbPut(db, leafId, value); // one small write per leaf, not the whole growing object
    await sleep(DELAY_MS);
  }

  console.log("Done! Downloading requirements_by_leaf.json...");
  downloadJson("requirements_by_leaf.json", results);
  await idbClear(db);
  console.log("All 3 files downloaded. Hand them to 02b_import_browser_export.py.");
})();
