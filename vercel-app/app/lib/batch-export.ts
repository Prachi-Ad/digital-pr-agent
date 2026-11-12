/**
 * One CSV for a whole batch, shaped so Google Sheets (or Excel) opens it with a
 * usable table: one row per record, a record_type column to filter on, and every
 * field needed to proceed without opening the app again.
 *
 * CSV rather than XLSX on purpose: no dependency, no build weight, and Sheets
 * imports it directly (File -> Import, or just drag it into a sheet).
 */

export type BatchExportInput = {
  analyses: Array<{ url: string; analysis: any }>;
  opportunities: any[];
  listicles: any[];
  drafts: Record<string, any>;
  listicleDrafts: Record<string, any>;
  outcomes: Record<string, any>;
  angle?: string;
  theme?: string;
};

const HEADERS = [
  "record_type",
  "workflow",
  "theme",
  "publication",
  "title",
  "url",
  "placement",
  "fit",
  "score",
  "confidence",
  "why_it_matters",
  "evidence",
  "subject",
  "body",
  "status",
  "coverage_url",
  "next_action",
];

function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
}

/** RFC 4180: quote when the value contains a comma, quote, or newline. */
function cell(value: unknown): string {
  const value_ = text(value);
  return /[",\n]/.test(value_) ? `"${value_.replace(/"/g, '""')}"` : value_;
}

function row(values: unknown[]): string {
  return values.map(cell).join(",");
}

function draftRow(
  type: string,
  workflow: string,
  draft: any,
  outcome: any,
  fallbackTheme: string
): string {
  return row([
    type,
    workflow,
    fallbackTheme,
    text(draft?.publication),
    text(draft?.target_title),
    text(draft?.target_url),
    text(draft?.channel),
    "",
    "",
    "",
    "",
    text(draft?.personalization_evidence),
    text(draft?.subject_line),
    text(draft?.message_body),
    text(outcome?.status || "Draft"),
    text(outcome?.coverage_url),
    text(draft?.call_to_action),
  ]);
}

export function buildBatchCsv(input: BatchExportInput): string {
  const lines: string[] = [HEADERS.join(",")];
  const angleTheme = text(input.angle);
  const listicleTheme = text(input.theme);

  for (const item of input.analyses || []) {
    const analysis = item?.analysis || {};
    lines.push(
      row([
        "Article",
        "Digital PR",
        angleTheme,
        "",
        text(analysis.article_title || item.url),
        text(item.url),
        "",
        "",
        "",
        "",
        text(analysis.assessment),
        text((analysis.key_claims || []).join("; ")),
        "",
        "",
        "",
        "",
        "",
      ])
    );
    for (const angle of analysis.pr_angles || []) {
      lines.push(
        row([
          "PR angle",
          "Digital PR",
          text(angle.angle),
          "",
          text(analysis.article_title || item.url),
          text(item.url),
          text(angle.story_type),
          text(angle.recommended_tactic),
          "",
          text(angle.confidence),
          text(angle.why_useful),
          text(angle.evidence),
          "",
          "",
          "",
          "",
          text(angle.next_action),
        ])
      );
    }
  }

  for (const opportunity of input.opportunities || []) {
    lines.push(
      row([
        "Opportunity",
        "Digital PR",
        angleTheme,
        text(opportunity?.publication),
        text(opportunity?.article_title),
        text(opportunity?.article_url),
        text(opportunity?.opportunity_type),
        text(opportunity?.pr_fit),
        text(opportunity?.pr_score),
        text(opportunity?.confidence),
        text(opportunity?.why_relevant),
        text(opportunity?.evidence),
        "",
        "",
        "",
        "",
        text(opportunity?.recommended_action),
      ])
    );
  }

  for (const item of input.listicles || []) {
    lines.push(
      row([
        "Listicle",
        "Listicles",
        listicleTheme,
        text(item?.publication),
        text(item?.listicle_title),
        text(item?.listicle_url),
        text(item?.placement_type),
        text(item?.pr_fit || item?.brand_fit),
        "",
        text(item?.confidence),
        text(item?.inclusion_gap),
        text(item?.evidence),
        "",
        "",
        "",
        "",
        "",
      ])
    );
  }

  for (const [id, draft] of Object.entries(input.drafts || {})) {
    lines.push(draftRow("Draft", "Digital PR", draft, input.outcomes?.[id], angleTheme));
  }
  for (const [id, draft] of Object.entries(input.listicleDrafts || {})) {
    lines.push(draftRow("Listicle draft", "Listicles", draft, input.outcomes?.[id], listicleTheme));
  }

  return lines.join("\r\n");
}

export function batchFileName(prefix = "vista-batch"): string {
  const now = new Date();
  const stamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
    "-",
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
  ].join("");
  return `${prefix}-${stamp}.csv`;
}

/** Builds and downloads the CSV. Returns the row count (header excluded). */
export function downloadBatchCsv(input: BatchExportInput, prefix?: string): number {
  const csv = buildBatchCsv(input);
  // The BOM keeps Sheets and Excel from mangling non-ASCII names.
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = batchFileName(prefix);
  link.click();
  URL.revokeObjectURL(url);
  return Math.max(0, csv.split("\r\n").length - 1);
}
