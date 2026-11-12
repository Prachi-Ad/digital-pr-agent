const MARKDOWN = `# PR Research Agent

> A private Digital PR, SEO, and AEO research tool by Prachi Admane. It analyzes published articles, finds editorial opportunities, scores them for search and answer-engine fit, writes pitches to a publication's editorial team, and logs a batch to one Google Sheet. It does not send email and does not research individual people.

## How it works

1. **Research** — paste a published article. The tool extracts credible angles and evidence.
2. **Prospects** — review real articles and editorial openings. Each gets a fit verdict: Strong, Possible, Weak, or Not suitable.
3. **Outreach** — write a 70–150 word pitch to the publication's editorial team, then copy, download, or sync the batch. No recipient names or personal email addresses are collected.

## Skill

- [SEO / AEO / Digital PR skill](/skills/seo-aeo-digital-pr.md): methodology, scoring rubric, AEO checklist, output contract.

## Summary

- [llms.txt](/llms.txt): compact machine-readable summary.
- API: token-gated POST \`/api/analyze\` with actions \`analyze\`, \`domain-scan\`, \`own-pages\`, \`opportunities\`, \`draft\`, \`listicles\`, \`listicle-draft\`, \`publisher-policy\`, \`site-metrics\`.

## Rules

- No people research: no names, roles, or email addresses are looked up or invented.
- Never invent statistics, citations, contacts, policies, or coverage.
- Paid, sponsored, affiliate, and directory routes are labeled honestly.
- A human reviews every draft. The tool does not send.

## Interactive app

The full interface is at [https://pr.prachiadmane.com/](https://pr.prachiadmane.com/) and requires JavaScript. Fetch [llms.txt](/llms.txt) or [the skill](/skills/seo-aeo-digital-pr.md) for plain-text access.
`;

export async function GET() {
  return new Response(MARKDOWN, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Cache-Control": "public, max-age=300",
      Vary: "User-Agent, Accept",
    },
  });
}
