const TOKEN = "PASTE_YOUR_TOKEN_HERE"; // keep the token from your current script

const TABS = {
  Pitches: ["key","date","angle","publication","site_domain","article_title","article_url","used","pr_fit","pr_score","contact_name","contact_role","email","subject","body","status","coverage_url"],
  Contacts: ["key","name","publication","role","beat","email","contact_page","profile_url","source_article","source_url","last_angle","last_seen","status"],
  Coverage: ["key","date","contact_name","publication","article_title","article_url","subject","coverage_url","status"]
};

const WIDTHS = {
  Pitches: [90,90,180,150,120,220,240,55,100,70,140,130,190,230,420,110,220],
  Contacts: [120,150,150,130,150,190,190,190,220,240,180,90,110],
  Coverage: [90,90,150,150,220,240,230,230,100]
};

const DASH = "Dashboard";
const INDIGO = "#5b5bd6";
const INDIGO_DARK = "#4646c6";
const SOFT = "#eeefff";
const INK = "#17182b";
const MUTED = "#5f6278";

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

  const head = sh.getRange(1, 1, 1, n);
  head.setBackground(INDIGO_DARK)
      .setFontColor("#ffffff")
      .setFontWeight("bold")
      .setFontSize(10)
      .setVerticalAlignment("middle")
      .setWrap(false);
  sh.setRowHeight(1, 34);

  for (let i = 1; i <= n; i++) sh.setColumnWidth(i, WIDTHS[name][i - 1] || 140);

  if (lastRow > 1) {
    const body = sh.getRange(2, 1, lastRow - 1, n);
    body.setVerticalAlignment("top").setFontSize(10).setFontColor(INK);
    body.setBorder(true, true, true, true, true, true, "#e4e6f0", SpreadsheetApp.BorderStyle.SOLID);

    if (name === "Pitches") {
      sh.getRange(2, 15, lastRow - 1, 1).setWrap(true);   // body
      sh.getRange(2, 14, lastRow - 1, 1).setWrap(true);   // subject
      sh.getRange(2, 10, lastRow - 1, 1).setHorizontalAlignment("center").setNumberFormat("0");
      sh.getRange(2, 2, lastRow - 1, 1).setNumberFormat("yyyy-mm-dd");
    }
    if (name === "Contacts") {
      sh.getRange(2, 12, lastRow - 1, 1).setNumberFormat("yyyy-mm-dd");
    }
    if (name === "Coverage") {
      sh.getRange(2, 2, lastRow - 1, 1).setNumberFormat("yyyy-mm-dd");
    }
  }

  try {
    const filter = sh.getFilter();
    if (filter) filter.remove();
  } catch (e) {}
  try {
    sh.getRange(1, 1, Math.max(lastRow, 2), n).createFilter();
  } catch (e) {}

  // Status pill colours
  const statusCol = name === "Pitches" ? 16 : (name === "Contacts" ? 13 : 9);
  const rules = sh.getConditionalFormatRules().filter(r => false);
  sh.clearConditionalFormatRules();
  Object.keys(STATUS_COLORS).forEach(st => {
    const [bg, fg] = STATUS_COLORS[st];
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(st)
      .setBackground(bg)
      .setFontColor(fg)
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
  const put = (a, b, c) => rows.push([a ?? "", b ?? "", c ?? ""]);
  const blank = () => put("", "", "");

  put("Vista PR · Pitch Dashboard", "", "");
  put("Last sync", new Date().toISOString().replace("T", " ").slice(0, 16) + " UTC", "");
  blank();
  put("PIPELINE", "", "");
  put("Total pitches", '=COUNTA(Pitches!A2:A)', "");
  put("Draft", '=COUNTIF(Pitches!P2:P,"Draft")', "");
  put("Pitched", '=COUNTIF(Pitches!P2:P,"Pitched")', "");
  put("Replied", '=COUNTIF(Pitches!P2:P,"Replied")', "");
  put("Covered", '=COUNTIF(Pitches!P2:P,"Covered")', "");
  put("Declined", '=COUNTIF(Pitches!P2:P,"Declined")', "");
  put("Do not contact", '=COUNTIF(Pitches!P2:P,"Do not contact")', "");
  blank();
  put("PERFORMANCE", "", "");
  put("Reply rate", '=IFERROR(COUNTIF(Pitches!P2:P,"Replied")/COUNTA(Pitches!A2:A),0)', "");
  put("Coverage rate", '=IFERROR(COUNTIF(Pitches!P2:P,"Covered")/COUNTA(Pitches!A2:A),0)', "");
  put("Emails found", '=COUNTA(Pitches!M2:M)&" of "&COUNTA(Pitches!A2:A)', "");
  put("Average PR score", '=IFERROR(ROUND(AVERAGE(Pitches!J2:J),0),0)', "");
  put("Strong-fit targets", '=COUNTIF(Pitches!I2:I,"Strong fit")', "");
  put("Used articles", '=COUNTIF(Pitches!H2:H,"yes")', "");
  blank();
  put("MEDIA LIBRARY", "", "");
  put("Saved contacts", '=IFERROR(COUNTA(Contacts!B2:B),0)', "");
  put("Contacts with email", '=IFERROR(COUNTA(Contacts!F2:F),0)', "");
  put("Outlets covered", '=IFERROR(COUNTA(UNIQUE(FILTER(Contacts!C2:C,Contacts!C2:C<>""))),0)', "");
  blank();
  put("PITCHES BY PUBLICATION", "", "");
  put('=IFERROR(QUERY(Pitches!A2:Q,"select D, count(A) where D is not null group by D order by count(A) desc label D \'Publication\', count(A) \'Pitches\'",0),"No data yet")', "", "");

  sh.getRange(1, 1, rows.length, 3).setValues(rows.map(r => [r[0] ?? "", r[1] ?? "", r[2] ?? ""]));

  // Title
  sh.getRange("A1:C1").merge()
    .setBackground(INDIGO_DARK)
    .setFontColor("#ffffff")
    .setFontSize(16)
    .setFontWeight("bold")
    .setVerticalAlignment("middle")
    .setHorizontalAlignment("left");
  sh.setRowHeight(1, 46);

  sh.getRange("A2:B2").setFontColor(MUTED).setFontSize(10);

  // Section headers
  ["A4", "A15", "A23"].forEach(function (a) {
    sh.getRange(a + ":C" + a)
      .merge()
      .setBackground(SOFT)
      .setFontColor(INDIGO_DARK)
      .setFontWeight("bold")
      .setFontSize(10)
      .setVerticalAlignment("middle");
    sh.setRowHeight(+a.slice(1), 30);
  });

  // Metric label/value blocks
  const blocks = [["A5", "A14"], ["A16", "A22"], ["A24", "A27"]];
  blocks.forEach(function (b) {
    const start = +b[0].slice(1), end = +b[1].slice(1);
    const rng = sh.getRange("A" + start + ":B" + end);
    rng.setBorder(true, true, true, true, true, true, "#e4e6f0", SpreadsheetApp.BorderStyle.SOLID);
    rng.setVerticalAlignment("middle");
    sh.getRange("A" + start + ":A" + end).setFontColor(MUTED).setFontSize(10);
    sh.getRange("B" + start + ":B" + end)
      .setFontColor(INK)
      .setFontWeight("bold")
      .setFontSize(12)
      .setHorizontalAlignment("right");
    for (let r = start; r <= end; r++) sh.setRowHeight(r, 30);
  });

  sh.getRange("B17:B18").setNumberFormat("0%");
  sh.getRange("B20:B21").setNumberFormat("0");
  sh.getRange("B25:B26").setNumberFormat("0");

  // Publication table styling
  const pub = rows.length;
  try {
    const vals = sh.getRange("A" + pub + ":B" + (pub + 40)).getValues();
    let last = 0;
    for (let i = 0; i < vals.length; i++) {
      if (String(vals[i][0]).trim() !== "" || String(vals[i][1]).trim() !== "") last = i;
    }
    if (last > 0) {
      const t = sh.getRange(pub, 1, last + 1, 2);
      t.setBorder(true, true, true, true, true, true, "#e4e6f0", SpreadsheetApp.BorderStyle.SOLID);
      sh.getRange(pub, 1, 1, 2)
        .setBackground(INDIGO)
        .setFontColor("#ffffff")
        .setFontWeight("bold")
        .setFontSize(10);
      sh.getRange(pub + 1, 1, last, 2).setFontSize(10).setVerticalAlignment("middle");
      sh.getRange(pub + 1, 2, last, 1).setHorizontalAlignment("right");
    }
  } catch (e) {}

  sh.setFrozenRows(2);
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.token !== TOKEN) return out({ detail: "forbidden" });
    const tab = body.tab || "Pitches";
    if (!TABS[tab]) return out({ detail: "Unknown tab." });

    const headers = TABS[tab];
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
      const row = headers.map(function (h) { return o[h] ?? ""; });
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
      sh.getRange(last + 1, 1, toAppend.length, headers.length).setValues(toAppend);
      sh.getRange(last + 1, 1, toAppend.length, headers.length)
        .setBorder(true, true, true, true, true, true, "#e4e6f0", SpreadsheetApp.BorderStyle.SOLID)
        .setVerticalAlignment("top")
        .setFontSize(10)
        .setFontColor(INK);
      if (tab === "Pitches") {
        sh.getRange(last + 1, 15, toAppend.length, 1).setWrap(true);
        sh.getRange(last + 1, 14, toAppend.length, 1).setWrap(true);
        sh.getRange(last + 1, 10, toAppend.length, 1).setHorizontalAlignment("center").setNumberFormat("0");
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
