const TOKEN = "PASTE_YOUR_TOKEN_HERE";

const TABS = {
  Pitches: ["key","date","angle","publication","site_domain","article_title","article_url","used","pr_fit","pr_score","contact_name","contact_role","email","subject","body","status","coverage_url"],
  Listicles: ["key","date","publication","listicle_title","listicle_url","placement_type","contact_name","contact_role","email","subject","body","status","coverage_url"],
  Contacts: ["key","name","publication","role","beat","email","contact_page","profile_url","source_article","source_url","last_angle","last_seen","status"],
  Coverage: ["key","date","contact_name","publication","article_title","article_url","subject","coverage_url","status"]
};

const WIDTHS = {
  Pitches: [90,90,180,150,120,220,240,55,100,70,140,130,190,230,420,110,220],
  Listicles: [120,90,150,240,240,110,150,130,190,230,420,110,240],
  Contacts: [120,150,150,130,150,190,190,190,220,240,180,90,110],
  Coverage: [90,90,150,150,220,240,230,230,100]
};

const STATUS_COL = { Pitches: 16, Listicles: 12, Contacts: 13, Coverage: 9 };

const DASH = "Dashboard";
const INDIGO = "#5b5bd6";
const INDIGO_DARK = "#4646c6";
const SOFT = "#eeefff";
const INK = "#17182b";
const MUTED = "#5f6278";
const LINE = "#e4e6f0";

const STATUS_COLORS = {
  "Covered": ["#e8f7ee", "#047857"],
  "Replied": ["#eef2ff", "#4338ca"],
  "Pitched": ["#fffbeb", "#b45309"],
  "Declined": ["#fef2f2", "#b91c1c"],
  "Do not contact": ["#f1f2f8", "#6b6e85"],
  "Draft": ["#f7f8fd", "#5f6278"]
};

function ss() { return SpreadsheetApp.getActiveSpreadsheet(); }

function getTab(name) {
  let sh = ss().getSheetByName(name);
  if (!sh) {
    sh = ss().insertSheet(name);
    sh.getRange(1, 1, 1, TABS[name].length).setValues([TABS[name]]);
  }
  styleTab(name, sh);
  return sh;
}

function styleTab(name, sh) {
  const headers = TABS[name];
  const n = headers.length;
  const lastRow = Math.max(sh.getLastRow(), 1);

  sh.setFrozenRows(1);
  sh.setFrozenColumns(1);

  sh.getRange(1, 1, 1, n)
    .setBackground(INDIGO_DARK)
    .setFontColor("#ffffff")
    .setFontWeight("bold")
    .setFontSize(10)
    .setVerticalAlignment("middle")
    .setWrap(false);
  sh.setRowHeight(1, 34);

  for (let i = 1; i <= n; i++) sh.setColumnWidth(i, WIDTHS[name][i - 1] || 140);

  if (lastRow > 1) {
    sh.getRange(2, 1, lastRow - 1, n)
      .setVerticalAlignment("top")
      .setFontSize(10)
      .setFontColor(INK)
      .setBorder(true, true, true, true, true, true, LINE, SpreadsheetApp.BorderStyle.SOLID);

    if (name === "Pitches") {
      sh.getRange(2, 15, lastRow - 1, 1).setWrap(true);
      sh.getRange(2, 14, lastRow - 1, 1).setWrap(true);
      sh.getRange(2, 10, lastRow - 1, 1).setHorizontalAlignment("center").setNumberFormat("0");
      sh.getRange(2, 2, lastRow - 1, 1).setNumberFormat("yyyy-mm-dd");
    }
    if (name === "Listicles") {
      sh.getRange(2, 11, lastRow - 1, 1).setWrap(true);
      sh.getRange(2, 10, lastRow - 1, 1).setWrap(true);
      sh.getRange(2, 2, lastRow - 1, 1).setNumberFormat("yyyy-mm-dd");
    }
    if (name === "Contacts") sh.getRange(2, 12, lastRow - 1, 1).setNumberFormat("yyyy-mm-dd");
    if (name === "Coverage") sh.getRange(2, 2, lastRow - 1, 1).setNumberFormat("yyyy-mm-dd");
  }

  try { const f = sh.getFilter(); if (f) f.remove(); } catch (e) {}
  try { sh.getRange(1, 1, Math.max(lastRow, 2), n).createFilter(); } catch (e) {}

  const statusCol = STATUS_COL[name];
  const rules = [];
  sh.clearConditionalFormatRules();
  Object.keys(STATUS_COLORS).forEach(function (st) {
    const c = STATUS_COLORS[st];
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(st)
      .setBackground(c[0])
      .setFontColor(c[1])
      .setBold(true)
      .setRanges([sh.getRange(2, statusCol, 1000, 1)])
      .build());
  });
  if (name === "Pitches") {
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo("Strong fit").setFontColor("#047857").setBold(true)
      .setRanges([sh.getRange(2, 9, 1000, 1)]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo("Not suitable").setFontColor("#b91c1c").setBold(true)
      .setRanges([sh.getRange(2, 9, 1000, 1)]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenNumberGreaterThanOrEqualTo(70).setBackground("#ecfdf5").setFontColor("#047857")
      .setRanges([sh.getRange(2, 10, 1000, 1)]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenNumberLessThan(40).setBackground("#fef2f2").setFontColor("#b91c1c")
      .setRanges([sh.getRange(2, 10, 1000, 1)]).build());
  }
  sh.setConditionalFormatRules(rules);
}

function ensureDashboard() {
  let sh = ss().getSheetByName(DASH);
  if (!sh) sh = ss().insertSheet(DASH, 0);
  sh.clear();
  sh.clearConditionalFormatRules();
  try { const f = sh.getFilter(); if (f) f.remove(); } catch (e) {}
  sh.setHiddenGridlines(true);

  for (let c = 1; c <= 6; c++) sh.setColumnWidth(c, c === 1 ? 250 : 150);

  const rows = [];
  const sections = [];
  const blocks = [];
  const percents = [];
  const ints = [];
  const queries = [];
  let blockStart = 0;

  function put(a, b) { rows.push([a || "", b || "", ""]); }
  function blank() { rows.push(["", "", ""]); }
  function row() { return rows.length; }
  function section(title) {
    blank();
    put(title, "");
    sections.push(row());
  }
  function blockStartMark() { blockStart = row() + 1; }
  function blockEndMark(kind) {
    const end = row();
    if (end >= blockStart) {
      blocks.push([blockStart, end]);
      if (kind === "percent") for (let r = blockStart; r <= end; r++) percents.push(r);
      if (kind === "int") for (let r = blockStart; r <= end; r++) ints.push(r);
    }
  }

  put("Vista PR · Pitch Dashboard", "");
  put("Last sync", new Date().toISOString().replace("T", " ").slice(0, 16) + " UTC", "");

  section("DIGITAL PR PIPELINE");
  blockStartMark();
  put("Total pitches", '=COUNTA(Pitches!A2:A)');
  put("Draft", '=COUNTIF(Pitches!P2:P,"Draft")');
  put("Pitched", '=COUNTIF(Pitches!P2:P,"Pitched")');
  put("Replied", '=COUNTIF(Pitches!P2:P,"Replied")');
  put("Covered", '=COUNTIF(Pitches!P2:P,"Covered")');
  put("Declined", '=COUNTIF(Pitches!P2:P,"Declined")');
  put("Do not contact", '=COUNTIF(Pitches!P2:P,"Do not contact")');
  blockEndMark("int");

  section("LISTICLE INCLUSION");
  blockStartMark();
  put("Total requests", '=IFERROR(COUNTA(Listicles!A2:A),0)');
  put("Draft", '=IFERROR(COUNTIF(Listicles!L2:L,"Draft"),0)');
  put("Pitched", '=IFERROR(COUNTIF(Listicles!L2:L,"Pitched"),0)');
  put("Replied", '=IFERROR(COUNTIF(Listicles!L2:L,"Replied"),0)');
  put("Covered", '=IFERROR(COUNTIF(Listicles!L2:L,"Covered"),0)');
  put("Declined", '=IFERROR(COUNTIF(Listicles!L2:L,"Declined"),0)');
  blockEndMark("int");

  section("PERFORMANCE");
  blockStartMark();
  put("Digital reply rate", '=IFERROR(COUNTIF(Pitches!P2:P,"Replied")/COUNTA(Pitches!A2:A),0)');
  put("Digital coverage rate", '=IFERROR(COUNTIF(Pitches!P2:P,"Covered")/COUNTA(Pitches!A2:A),0)');
  put("Listicle coverage rate", '=IFERROR(COUNTIF(Listicles!L2:L,"Covered")/COUNTA(Listicles!A2:A),0)');
  blockEndMark("percent");
  blockStartMark();
  put("Emails found", '=COUNTA(Pitches!M2:M)&" of "&COUNTA(Pitches!A2:A)');
  put("Average PR score", '=IFERROR(ROUND(AVERAGE(Pitches!J2:J),0),0)');
  put("Strong-fit targets", '=COUNTIF(Pitches!I2:I,"Strong fit")');
  put("Used articles", '=COUNTIF(Pitches!H2:H,"yes")');
  blockEndMark("int");

  section("MEDIA LIBRARY");
  blockStartMark();
  put("Saved contacts", '=IFERROR(COUNTA(Contacts!B2:B),0)');
  put("Contacts with email", '=IFERROR(COUNTA(Contacts!F2:F),0)');
  put("Outlets covered", '=IFERROR(COUNTA(UNIQUE(FILTER(Contacts!C2:C,Contacts!C2:C<>""))),0)');
  blockEndMark("int");

  section("PITCHES BY PUBLICATION");
  queries.push(row() + 1);
  put('=IFERROR(QUERY(Pitches!A2:Q,"select D, count(A) where D is not null group by D order by count(A) desc label D \'Publication\', count(A) \'Pitches\'",0),"No data yet")');

  section("LISTICLES BY OUTLET");
  queries.push(row() + 1);
  put('=IFERROR(QUERY(Listicles!A2:M,"select C, count(A) where C is not null group by C order by count(A) desc label C \'Outlet\', count(A) \'Requests\'",0),"No data yet")');

  sh.getRange(1, 1, rows.length, 3).setValues(rows.map(function (r) { return [r[0], r[1], r[2]]; }));

  sh.getRange("A1:C1").merge()
    .setBackground(INDIGO_DARK)
    .setFontColor("#ffffff")
    .setFontSize(16)
    .setFontWeight("bold")
    .setVerticalAlignment("middle")
    .setHorizontalAlignment("left");
  sh.setRowHeight(1, 46);
  sh.getRange("A2:B2").setFontColor(MUTED).setFontSize(10);

  sections.forEach(function (r) {
    sh.getRange(r, 1, 1, 3)
      .merge()
      .setBackground(SOFT)
      .setFontColor(INDIGO_DARK)
      .setFontWeight("bold")
      .setFontSize(10)
      .setVerticalAlignment("middle");
    sh.setRowHeight(r, 30);
  });

  blocks.forEach(function (b) {
    const s = b[0], e = b[1];
    sh.getRange(s, 1, e - s + 1, 2)
      .setBorder(true, true, true, true, true, true, LINE, SpreadsheetApp.BorderStyle.SOLID)
      .setVerticalAlignment("middle");
    sh.getRange(s, 1, e - s + 1, 1).setFontColor(MUTED).setFontSize(10);
    sh.getRange(s, 2, e - s + 1, 1)
      .setFontColor(INK).setFontWeight("bold").setFontSize(12).setHorizontalAlignment("right");
    for (let r = s; r <= e; r++) sh.setRowHeight(r, 30);
  });

  percents.forEach(function (r) { sh.getRange(r, 2).setNumberFormat("0%"); });
  ints.forEach(function (r) { sh.getRange(r, 2).setNumberFormat("0"); });

  queries.forEach(function (r) {
    try {
      const vals = sh.getRange(r, 1, 60, 2).getValues();
      let last = 0;
      for (let i = 0; i < vals.length; i++) {
        if (String(vals[i][0]).trim() !== "" || String(vals[i][1]).trim() !== "") last = i;
      }
      if (last > 0) {
        sh.getRange(r, 1, last + 1, 2)
          .setBorder(true, true, true, true, true, true, LINE, SpreadsheetApp.BorderStyle.SOLID);
        sh.getRange(r, 1, 1, 2)
          .setBackground(INDIGO).setFontColor("#ffffff").setFontWeight("bold").setFontSize(10);
        sh.getRange(r + 1, 1, last, 2).setFontSize(10).setVerticalAlignment("middle");
        sh.getRange(r + 1, 2, last, 1).setHorizontalAlignment("right");
      }
    } catch (e) {}
  });

  sh.setFrozenRows(2);
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.token !== TOKEN) return out({ detail: "forbidden" });
    const tab = body.tab || "Pitches";
    if (!TABS[tab]) return out({ detail: "Unknown tab." });

    const headers = TABS[tab];

    // Explicit clear: deletes data rows, keeps the two header rows and the
    // formatting. Only ever runs when the app sends action:"clear".
    if (body.action === "clear") {
      const sh = getTab(tab);
      const last = sh.getLastRow();
      const cleared = last > 2 ? last - 2 : 0;
      if (cleared > 0) {
        sh.getRange(3, 1, cleared, Math.max(sh.getLastColumn(), headers.length)).clearContent();
      }
      return out({ ok: true, cleared: cleared, tab: tab });
    }

    const incoming = Array.isArray(body.rows) ? body.rows : [];
    if (!incoming.length) return out({ detail: "No rows." });

    const sh = getTab(tab);
    const last = Math.max(sh.getLastRow(), 1);
    const existing = last > 1
      ? sh.getRange(2, 1, last - 1, 1).getValues().map(function (r) { return String(r[0] || ""); })
      : [];

    let updated = 0, appended = 0;
    const toAppend = [];

    incoming.forEach(function (o) {
      const row = headers.map(function (h) { return o[h] !== undefined && o[h] !== null ? o[h] : ""; });
      const key = String(row[0] || "");
      if (!key) return;
      const idx = existing.indexOf(key);
      if (idx >= 0) {
        sh.getRange(idx + 2, 1, 1, headers.length).setValues([row]);
        updated++;
      } else {
        toAppend.push(row);
        existing.push(key);
        appended++;
      }
    });

    if (toAppend.length) {
      const rng = sh.getRange(last + 1, 1, toAppend.length, headers.length);
      rng.setValues(toAppend)
        .setBorder(true, true, true, true, true, true, LINE, SpreadsheetApp.BorderStyle.SOLID)
        .setVerticalAlignment("top")
        .setFontSize(10)
        .setFontColor(INK);
      if (tab === "Pitches") {
        sh.getRange(last + 1, 15, toAppend.length, 1).setWrap(true);
        sh.getRange(last + 1, 14, toAppend.length, 1).setWrap(true);
        sh.getRange(last + 1, 10, toAppend.length, 1).setHorizontalAlignment("center").setNumberFormat("0");
        sh.getRange(last + 1, 2, toAppend.length, 1).setNumberFormat("yyyy-mm-dd");
      }
      if (tab === "Listicles") {
        sh.getRange(last + 1, 11, toAppend.length, 1).setWrap(true);
        sh.getRange(last + 1, 10, toAppend.length, 1).setWrap(true);
        sh.getRange(last + 1, 2, toAppend.length, 1).setNumberFormat("yyyy-mm-dd");
      }
      if (tab === "Contacts") sh.getRange(last + 1, 12, toAppend.length, 1).setNumberFormat("yyyy-mm-dd");
      if (tab === "Coverage") sh.getRange(last + 1, 2, toAppend.length, 1).setNumberFormat("yyyy-mm-dd");
    }

    styleTab(tab, sh);
    ensureDashboard();

    return out({ ok: true, tab: tab, updated: updated, appended: appended });
  } catch (err) {
    return out({ detail: "Script error: " + String(err).slice(0, 200) });
  }
}

function out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
