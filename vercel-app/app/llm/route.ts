const MARKDOWN = `# PR Research Agent

> A private Digital PR, SEO, and AEO research tool by Prachi Admane. It analyzes published articles, finds editorial opportunities, scores them for search and answer-engine fit, researches writers and content/SEO contacts, and writes personalized pitches for human review. It does not send email.

## How it works

1. **Research** — paste a published article. The tool extracts credible angles and evidence.
2. **Prospects** — review real articles and editorial openings. Each gets a fit verdict: Strong, Possible, Weak, or Not suitable.
3. **Contacts** — find the bylined writer, content manager, SEO lead, or link-building contact. If no writer matches, the tool falls back to the publication's verified content/SEO contact.
4. **Outreach** — write a personalized 120–180 word pitch, copy or download it, and send it yourself.

## Skill

- [SEO / AEO / Digital PR skill](/skills/seo-aeo-digital-pr.md): methodology, scoring rubric, AEO checklist, contact rules, output contract.

## Summary

- [llms.txt](/llms.txt): compact machine-readable summary.
- API: token-gated POST \`/api/analyze\` with actions \`analyze\`, \`opportunities\`, \`journalists\`, \`draft\`, \`listicles\`, \`listicle-contact\`, \`publisher-policy\`.

## Rules

- Only use emails explicitly published on public pages.
- Never guess an email pattern.
- Never invent statistics, citations, contacts, policies, or coverage.
- Paid, sponsored, affiliate, and directory routes are labeled honestly.
- A human reviews every contact and every draft. The tool does not send.

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
