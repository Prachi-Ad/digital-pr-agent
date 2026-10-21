"use client";
import { useState } from "react";
import { Loader2, Search, Users, FileText, List, Mail, Shield } from "lucide-react";

type AnyObj = Record<string, any>;

async function callApi(action: string, body: any = {}, onRetry?: (attempt: number) => void) {
  const maxAttempts = 3;
  let lastErr: any = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...body }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error || "Request failed");
      return data;
    } catch (err: any) {
      lastErr = err;
      if (attempt < maxAttempts) {
        if (onRetry) onRetry(attempt + 1);
        await new Promise((r) => setTimeout(r, 1500 * attempt));
      }
    }
  }
  throw lastErr;
}

function Spinner() {
  return <Loader2 className="animate-spin inline-block" size={18} />;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="text-xl font-semibold mb-2">{title}</h2>
      {children}
    </section>
  );
}

export default function Home() {
  const tabs = ["Analyze", "Opportunities", "Journalists", "Listicles", "Contact", "Policy"] as const;
  type Tab = (typeof tabs)[number];
  const [tab, setTab] = useState<Tab>("Analyze");
  const [retryMsg, setRetryMsg] = useState<string | null>(null);

  // Analyze state
  const [url, setUrl] = useState("");
  const [loadingAnalyze, setLoadingAnalyze] = useState(false);
  const [analysis, setAnalysis] = useState<AnyObj | null>(null);
  const [errAnalyze, setErrAnalyze] = useState<string | null>(null);

  // PR workflow state
  const [selectedAngle, setSelectedAngle] = useState<AnyObj | null>(null);
  const [loadingOpp, setLoadingOpp] = useState(false);
  const [opportunities, setOpportunities] = useState<AnyObj | null>(null);
  const [errOpp, setErrOpp] = useState<string | null>(null);

  const [selectedOpp, setSelectedOpp] = useState<AnyObj | null>(null);
  const [loadingJourn, setLoadingJourn] = useState(false);
  const [journalists, setJournalists] = useState<AnyObj | null>(null);
  const [errJourn, setErrJourn] = useState<string | null>(null);

  // Listicle state
  const [listForm, setListForm] = useState({
    search_theme: "",
    related_queries: "",
    target_audience: "All relevant audiences",
    target_market: "Global English-language",
    competitors: "Hootsuite, Sprout Social, Buffer, Later, SocialBee",
    max_results: 8,
  });
  const [loadingList, setLoadingList] = useState(false);
  const [listicles, setListicles] = useState<AnyObj | null>(null);
  const [errList, setErrList] = useState<string | null>(null);

  const [selectedItem, setSelectedItem] = useState<AnyObj | null>(null);
  const [loadingContact, setLoadingContact] = useState(false);
  const [contact, setContact] = useState<AnyObj | null>(null);
  const [errContact, setErrContact] = useState<string | null>(null);

  const [loadingPolicy, setLoadingPolicy] = useState(false);
  const [policy, setPolicy] = useState<AnyObj | null>(null);
  const [errPolicy, setErrPolicy] = useState<string | null>(null);

  async function analyze(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setLoadingAnalyze(true);
    setErrAnalyze(null);
    setRetryMsg(null);
    setAnalysis(null);
    try {
      const data = await callApi("analyze", { article_url: url.trim() }, (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`));
      setAnalysis(data);
    } catch (err: any) {
      setErrAnalyze(err?.message || "Something went wrong");
    } finally {
      setLoadingAnalyze(false);
      setRetryMsg(null);
    }
  }

  async function runOpportunities() {
    if (!selectedAngle) return;
    setLoadingOpp(true);
    setErrOpp(null);
    setRetryMsg(null);
    setOpportunities(null);
    try {
      const data = await callApi("opportunities", { angle: selectedAngle }, (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`));
      setOpportunities(data);
    } catch (err: any) {
      setErrOpp(err?.message || "Something went wrong");
    } finally {
      setLoadingOpp(false);
      setRetryMsg(null);
    }
  }

  async function runJournalists() {
    if (!selectedAngle || !selectedOpp) return;
    setLoadingJourn(true);
    setErrJourn(null);
    setRetryMsg(null);
    setJournalists(null);
    try {
      const data = await callApi("journalists", { angle: selectedAngle, opportunity: selectedOpp }, (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`));
      setJournalists(data);
    } catch (err: any) {
      setErrJourn(err?.message || "Something went wrong");
    } finally {
      setLoadingJourn(false);
      setRetryMsg(null);
    }
  }

  async function runListicles(e: React.FormEvent) {
    e.preventDefault();
    if (!listForm.search_theme.trim()) return;
    setLoadingList(true);
    setErrList(null);
    setRetryMsg(null);
    setListicles(null);
    try {
      const data = await callApi("listicles", {
        search_theme: listForm.search_theme.trim(),
        related_queries: listForm.related_queries,
        target_audience: listForm.target_audience,
        target_market: listForm.target_market,
        competitors: listForm.competitors.split(",").map((s) => s.trim()).filter(Boolean),
        max_results: Number(listForm.max_results) || 15,
      }, (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`));
      setListicles(data);
    } catch (err: any) {
      setErrList(err?.message || "Something went wrong");
    } finally {
      setLoadingList(false);
      setRetryMsg(null);
    }
  }

  async function runContact(item: AnyObj) {
    setSelectedItem(item);
    setTab("Contact");
    setLoadingContact(true);
    setErrContact(null);
    setRetryMsg(null);
    setContact(null);
    try {
      const data = await callApi("listicle-contact", { item }, (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`));
      setContact(data);
    } catch (err: any) {
      setErrContact(err?.message || "Something went wrong");
    } finally {
      setLoadingContact(false);
      setRetryMsg(null);
    }
  }

  async function runPolicy(item: AnyObj) {
    setSelectedItem(item);
    setTab("Policy");
    setLoadingPolicy(true);
    setErrPolicy(null);
    setRetryMsg(null);
    setPolicy(null);
    try {
      const data = await callApi("publisher-policy", { item }, (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`));
      setPolicy(data);
    } catch (err: any) {
      setErrPolicy(err?.message || "Something went wrong");
    } finally {
      setLoadingPolicy(false);
      setRetryMsg(null);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-3xl font-bold">Digital PR Agent</h1>
      <p className="mt-1 text-gray-600">AI research for Digital PR and listicle prospecting (Vercel build).</p>

      <nav className="mt-6 flex flex-wrap gap-2 border-b pb-2">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded px-3 py-1.5 text-sm ${tab === t ? "bg-blue-600 text-white" : "bg-gray-100 hover:bg-gray-200"}`}
          >
            {t}
          </button>
        ))}
      </nav>

      {retryMsg && (
        <div className="mt-4 rounded bg-blue-50 p-3 text-blue-700 text-sm">{retryMsg}</div>
      )}

      {tab === "Analyze" && (
        <>
          <form onSubmit={analyze} className="mt-6 flex gap-2">
            <input
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/article"
              className="flex-1 rounded border px-3 py-2"
            />
            <button type="submit" disabled={loadingAnalyze} className="flex items-center gap-2 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
              {loadingAnalyze ? <Spinner /> : <Search size={18} />}
              Analyze
            </button>
          </form>
          {errAnalyze && <div className="mt-4 rounded bg-red-50 p-3 text-red-700">{errAnalyze}</div>}
          {analysis && (
            <div className="mt-6 space-y-4">
              <div>
                <h2 className="text-2xl font-semibold">{analysis.article_title}</h2>
                <p className="text-gray-600">{analysis.main_topic}</p>
                <p className="mt-2 text-sm">{analysis.assessment}</p>
              </div>
              <div>
                <h3 className="text-xl font-semibold">PR angles ({analysis.pr_angles?.length || 0})</h3>
                <ul className="mt-2 space-y-3">
                  {analysis.pr_angles?.map((a: AnyObj, i: number) => (
                    <li key={i} className="rounded border bg-white p-4">
                      <div className="font-semibold">{a.angle}</div>
                      <div className="text-sm text-gray-500">{a.story_type} · {a.confidence}</div>
                      <p className="mt-2 text-sm">{a.story_hypothesis}</p>
                      <p className="mt-2 text-sm"><span className="font-medium">Contribution:</span> {a.brand_contribution}</p>
                      <p className="mt-2 text-sm"><span className="font-medium">Next action:</span> {a.next_action}</p>
                      <button
                        onClick={() => { setSelectedAngle(a); setTab("Opportunities"); }}
                        className="mt-3 rounded bg-gray-800 px-3 py-1.5 text-sm text-white"
                      >
                        Research opportunities →
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-xl font-semibold">Statistics ({analysis.statistics?.length || 0})</h3>
                <ul className="mt-2 space-y-1">
                  {analysis.statistics?.map((s: AnyObj, i: number) => (
                    <li key={i} className="text-sm">
                      <span className="font-medium">{s.statistic}</span> — {s.source} ({s.data_provenance})
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </>
      )}

      {tab === "Opportunities" && (
        <>
          {!selectedAngle && <p className="mt-6 text-gray-600">Analyze an article and pick an angle first.</p>}
          {selectedAngle && (
            <>
              <div className="mt-4 rounded border bg-white p-3 text-sm">
                <span className="font-medium">Selected angle:</span> {selectedAngle.angle}
              </div>
              <button
                onClick={runOpportunities}
                disabled={loadingOpp}
                className="mt-4 flex items-center gap-2 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
              >
                {loadingOpp ? <Spinner /> : <Search size={18} />} Run research
              </button>
              {errOpp && <div className="mt-4 rounded bg-red-50 p-3 text-red-700">{errOpp} <span className="block mt-1 text-sm">Tip: research can be flaky on Vercel; click "Run research" to retry, or use the local Streamlit app for heavy runs.</span></div>}
              {opportunities && (
                <div className="mt-6 space-y-3">
                  <p className="text-sm text-gray-600">{opportunities.research_summary}</p>
                  <ul className="space-y-3">
                    {opportunities.opportunities?.map((o: AnyObj, i: number) => (
                      <li key={i} className="rounded border bg-white p-4">
                        <div className="font-semibold">{o.article_title}</div>
                        <div className="text-sm text-gray-500">{o.publication} · {o.opportunity_type}</div>
                        <p className="mt-2 text-sm">{o.why_relevant}</p>
                        <p className="mt-1 text-sm"><span className="font-medium">Action:</span> {o.recommended_action}</p>
                        <a href={o.article_url} target="_blank" rel="noreferrer" className="mt-1 block text-sm text-blue-600 underline truncate">{o.article_url}</a>
                        <button
                          onClick={() => { setSelectedOpp(o); setTab("Journalists"); }}
                          className="mt-3 rounded bg-gray-800 px-3 py-1.5 text-sm text-white"
                        >
                          Research journalists →
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </>
      )}

      {tab === "Journalists" && (
        <>
          {!selectedAngle || !selectedOpp && <p className="mt-6 text-gray-600">Pick an opportunity first.</p>}
          {selectedAngle && selectedOpp && (
            <>
              <div className="mt-4 rounded border bg-white p-3 text-sm space-y-1">
                <div><span className="font-medium">Angle:</span> {selectedAngle.angle}</div>
                <div><span className="font-medium">Opportunity:</span> {selectedOpp.article_title} ({selectedOpp.publication})</div>
              </div>
              <button
                onClick={runJournalists}
                disabled={loadingJourn}
                className="mt-4 flex items-center gap-2 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
              >
                {loadingJourn ? <Spinner /> : <Users size={18} />} Run research
              </button>
              {errJourn && <div className="mt-4 rounded bg-red-50 p-3 text-red-700">{errJourn} <span className="block mt-1 text-sm">Tip: research can be flaky on Vercel; click "Run research" to retry.</span></div>}
              {journalists && (
                <div className="mt-6 space-y-3">
                  <p className="text-sm text-gray-600">{journalists.research_summary}</p>
                  <ul className="space-y-3">
                    {journalists.journalists?.map((j: AnyObj, i: number) => (
                      <li key={i} className="rounded border bg-white p-4">
                        <div className="font-semibold">{j.name}</div>
                        <div className="text-sm text-gray-500">{j.current_role} · {j.publication}</div>
                        <p className="mt-2 text-sm"><span className="font-medium">Relevant article:</span> {j.relevant_article_title}</p>
                        <a href={j.relevant_article_url} target="_blank" rel="noreferrer" className="block text-sm text-blue-600 underline truncate">{j.relevant_article_url}</a>
                        <p className="mt-2 text-sm">{j.why_relevant}</p>
                        <p className="mt-2 text-sm"><span className="font-medium">Pitch angle:</span> {j.suggested_pitch_angle}</p>
                        <p className="mt-1 text-sm text-gray-500">Confidence: {j.confidence}</p>
                      </li>
                    ))}
                  </ul>
                  {(!journalists.journalists || journalists.journalists.length === 0) && (
                    <p className="text-sm text-gray-600">No verified journalists found.</p>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}

      {tab === "Listicles" && (
        <>
          <form onSubmit={runListicles} className="mt-6 space-y-3">
            <div>
              <label className="block text-sm font-medium">Search theme *</label>
              <input
                required
                value={listForm.search_theme}
                onChange={(e) => setListForm({ ...listForm, search_theme: e.target.value })}
                placeholder="social media management tools"
                className="mt-1 w-full rounded border px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">Related queries</label>
              <input
                value={listForm.related_queries}
                onChange={(e) => setListForm({ ...listForm, related_queries: e.target.value })}
                placeholder="best social media tools, social media schedulers"
                className="mt-1 w-full rounded border px-3 py-2"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium">Target audience</label>
                <input
                  value={listForm.target_audience}
                  onChange={(e) => setListForm({ ...listForm, target_audience: e.target.value })}
                  className="mt-1 w-full rounded border px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium">Target market</label>
                <input
                  value={listForm.target_market}
                  onChange={(e) => setListForm({ ...listForm, target_market: e.target.value })}
                  className="mt-1 w-full rounded border px-3 py-2"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium">Competitors (comma-separated)</label>
              <input
                value={listForm.competitors}
                onChange={(e) => setListForm({ ...listForm, competitors: e.target.value })}
                className="mt-1 w-full rounded border px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium">Max results</label>
              <input
                type="number"
                min={5}
                max={20}
                value={listForm.max_results}
                onChange={(e) => setListForm({ ...listForm, max_results: Number(e.target.value) })}
                className="mt-1 w-32 rounded border px-3 py-2"
              />
            </div>
            <button type="submit" disabled={loadingList} className="flex items-center gap-2 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
              {loadingList ? <Spinner /> : <List size={18} />} Search listicles
            </button>
          </form>
          {errList && <div className="mt-4 rounded bg-red-50 p-3 text-red-700">{errList} <span className="block mt-1 text-sm">Tip: research can be flaky on Vercel; submit again to retry.</span></div>}
          {listicles && (
            <div className="mt-6 space-y-3">
              <p className="text-sm text-gray-600">{listicles.research_summary}</p>
              <ul className="space-y-3">
                {listicles.opportunities?.map((item: AnyObj, i: number) => (
                  <li key={i} className="rounded border bg-white p-4">
                    <div className="font-semibold">{item.listicle_title}</div>
                    <div className="text-sm text-gray-500">{item.publication} · {item.placement_type}</div>
                    <p className="mt-2 text-sm"><span className="font-medium">Fit:</span> {item.brand_fit}</p>
                    <p className="mt-1 text-sm"><span className="font-medium">Currently lists brand?</span> {item.brand_currently_listed}</p>
                    <p className="mt-1 text-sm"><span className="font-medium">Action:</span> {item.recommended_action}</p>
                    <a href={item.listicle_url} target="_blank" rel="noreferrer" className="mt-1 block text-sm text-blue-600 underline truncate">{item.listicle_url}</a>
                    <div className="mt-3 flex gap-2">
                      <button onClick={() => runContact(item)} className="rounded bg-gray-800 px-3 py-1.5 text-sm text-white flex items-center gap-1">
                        <Mail size={14} /> Find contact
                      </button>
                      <button onClick={() => runPolicy(item)} className="rounded bg-gray-800 px-3 py-1.5 text-sm text-white flex items-center gap-1">
                        <Shield size={14} /> Check policy
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
              {(!listicles.opportunities || listicles.opportunities.length === 0) && (
                <p className="text-sm text-gray-600">No candidates found.</p>
              )}
            </div>
          )}
        </>
      )}

      {tab === "Contact" && (
        <>
          {!selectedItem && <p className="mt-6 text-gray-600">Pick a listicle candidate first.</p>}
          {selectedItem && (
            <>
              <div className="mt-4 rounded border bg-white p-3 text-sm">
                <span className="font-medium">{selectedItem.listicle_title}</span> — {selectedItem.publication}
              </div>
              {loadingContact && <div className="mt-4"><Spinner /> Researching contact...</div>}
              {errContact && <div className="mt-4 rounded bg-red-50 p-3 text-red-700">{errContact}</div>}
              {contact && (
                <div className="mt-6 space-y-3">
                  <p className="text-sm text-gray-600">{contact.research_summary}</p>
                  <ul className="space-y-3">
                    {contact.contacts?.map((c: AnyObj, i: number) => (
                      <li key={i} className="rounded border bg-white p-4">
                        <div className="font-semibold">{c.contact_name}</div>
                        <div className="text-sm text-gray-500">{c.current_role}</div>
                        <p className="mt-2 text-sm"><span className="font-medium">Email:</span> {c.professional_email}</p>
                        <p className="mt-1 text-sm"><span className="font-medium">Method:</span> {c.contact_method}</p>
                        <p className="mt-1 text-sm">{c.why_this_contact}</p>
                        <p className="mt-1 text-sm text-gray-500">Confidence: {c.confidence}</p>
                        {c.source_url && c.source_url !== "Unknown" && (
                          <a href={c.source_url} target="_blank" rel="noreferrer" className="mt-1 block text-sm text-blue-600 underline truncate">{c.source_url}</a>
                        )}
                      </li>
                    ))}
                  </ul>
                  {(!contact.contacts || contact.contacts.length === 0) && (
                    <p className="text-sm text-gray-600">No verified contacts found.</p>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}

      {tab === "Policy" && (
        <>
          {!selectedItem && <p className="mt-6 text-gray-600">Pick a listicle candidate first.</p>}
          {selectedItem && (
            <>
              <div className="mt-4 rounded border bg-white p-3 text-sm">
                <span className="font-medium">{selectedItem.listicle_title}</span> — {selectedItem.publication}
              </div>
              {loadingPolicy && <div className="mt-4"><Spinner /> Checking policy...</div>}
              {errPolicy && <div className="mt-4 rounded bg-red-50 p-3 text-red-700">{errPolicy}</div>}
              {policy && (
                <div className="mt-6 space-y-3 rounded border bg-white p-4">
                  <div><span className="font-medium">Status:</span> {policy.policy_status}</div>
                  <div><span className="font-medium">Disposition:</span> {policy.recommended_disposition}</div>
                  <p className="mt-2 text-sm">{policy.policy_summary}</p>
                  <p className="mt-2 text-sm"><span className="font-medium">Reason:</span> {policy.disposition_reason}</p>
                  <p className="mt-2 text-sm"><span className="font-medium">Route:</span> {policy.recommended_route}</p>
                  {policy.policy_source_url && policy.policy_source_url !== "Unknown" && (
                    <a href={policy.policy_source_url} target="_blank" rel="noreferrer" className="mt-2 block text-sm text-blue-600 underline truncate">{policy.policy_source_url}</a>
                  )}
                  <p className="mt-2 text-sm text-gray-500">Confidence: {policy.confidence}</p>
                </div>
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}