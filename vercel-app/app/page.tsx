"use client";
import { useState } from "react";
import { Loader2, Search } from "lucide-react";

type Angle = {
  angle: string;
  story_type: string;
  recommended_tactic: string;
  story_hypothesis: string;
  why_useful: string;
  brand_contribution: string;
  target_publication_types: string[];
  target_journalist_beats: string[];
  relevant_asset: string;
  evidence: string;
  next_action: string;
  confidence: string;
};

type Analysis = {
  article_title: string;
  main_topic: string;
  target_audience: string[];
  key_claims: string[];
  statistics: { statistic: string; source: string; data_provenance: string; pr_relevance: string }[];
  useful_assets: string[];
  pr_angles: Angle[];
  assessment: string;
};

export default function Home() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Analysis | null>(null);

  async function analyze(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ article_url: url.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error || "Request failed");
      setResult(data as Analysis);
    } catch (err: any) {
      setError(err?.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-3xl font-bold">Digital PR Agent</h1>
      <p className="mt-2 text-gray-600">
        Turn a published article into PR angles and statistics. (Vercel build — analyze workflow first.)
      </p>

      <form onSubmit={analyze} className="mt-6 flex gap-2">
        <input
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/article"
          className="flex-1 rounded border px-3 py-2"
        />
        <button
          type="submit"
          disabled={loading}
          className="flex items-center gap-2 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {loading ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}
          Analyze
        </button>
      </form>

      {error && <div className="mt-4 rounded bg-red-50 p-3 text-red-700">{error}</div>}

      {result && (
        <section className="mt-8 space-y-6">
          <div>
            <h2 className="text-2xl font-semibold">{result.article_title}</h2>
            <p className="text-gray-600">{result.main_topic}</p>
            <p className="mt-2 text-sm">{result.assessment}</p>
          </div>

          <div>
            <h3 className="text-xl font-semibold">PR angles ({result.pr_angles.length})</h3>
            <ul className="mt-2 space-y-4">
              {result.pr_angles.map((a, i) => (
                <li key={i} className="rounded border bg-white p-4">
                  <div className="font-semibold">{a.angle}</div>
                  <div className="text-sm text-gray-500">{a.story_type} · {a.confidence}</div>
                  <p className="mt-2 text-sm">{a.story_hypothesis}</p>
                  <p className="mt-2 text-sm"><span className="font-medium">Contribution:</span> {a.brand_contribution}</p>
                  <p className="mt-2 text-sm"><span className="font-medium">Next action:</span> {a.next_action}</p>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="text-xl font-semibold">Statistics ({result.statistics.length})</h3>
            <ul className="mt-2 space-y-2">
              {result.statistics.map((s, i) => (
                <li key={i} className="text-sm">
                  <span className="font-medium">{s.statistic}</span> — {s.source} ({s.data_provenance})
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </main>
  );
}