// הדבק ב-Console של הדפדפן כשאתה על https://data.gov.il  (F12 -> Console).
// מאתר אוטומטית את הקובץ החודשי העדכני ביותר בכל מאגר (לא מזהה קבוע!),
// ומוריד: permit.json, business.json ו-opendata_meta.json (תאריכי הנתונים). שים את שלושתם בתיקייה opendata/.
(async () => {
  const PKGS = { permit: 'prvbuildingquirement', business: 'businessreq' };
  const api = p => fetch('/api/3/action/' + p).then(r => r.json()).then(j => j.result);
  const dateOf = name => { const m = /(\d{2})-(\d{2})-(\d{4})/.exec(name || ''); return m ? `${m[3]}-${m[2]}-${m[1]}` : ''; };
  const save = (obj, fname) => { const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(obj)], {type: 'application/json'})); a.download = fname; a.click(); };
  const meta = {};
  for (const [key, pkg] of Object.entries(PKGS)) {
    const res = (await api('package_show?id=' + pkg)).resources
      .filter(r => r.datastore_active && dateOf(r.name))
      .sort((a, b) => dateOf(b.name).localeCompare(dateOf(a.name)));
    const latest = res[0];
    console.log(key, '-> newest:', latest.name, latest.id);
    let records = [], offset = 0, total = 1;
    while (offset < total) {
      const j = await api(`datastore_search?resource_id=${latest.id}&limit=5000&offset=${offset}`);
      total = j.total; records = records.concat(j.records); offset += j.records.length;
      if (!j.records.length) break;
    }
    if (records.length !== total) throw new Error(`${key}: got ${records.length} of ${total} rows`);
    meta[key] = { resource_id: latest.id, name: latest.name, data_date: dateOf(latest.name), rows: total };
    save(records, key + '.json');
  }
  save(meta, 'opendata_meta.json');
  console.log(meta);
})();
