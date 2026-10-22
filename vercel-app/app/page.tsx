"use client";

import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  ExternalLink,
  FileText,
  LayoutGrid,
  List,
  Loader2,
  Mail,
  Plus,
  Search,
  Shield,
  SlidersHorizontal,
  Users,
  X,
} from "lucide-react";

type AnyObj = Record<string, any>;

const digitalSteps = ["Article", "PR angles", "Opportunities", "Journalists", "Outreach"] as const;
const listicleSteps = ["Search", "Prospects", "Outreach"] as const;
type DigitalStep = (typeof digitalSteps)[number];
type ListicleStep = (typeof listicleSteps)[number];
type Nav = "Workspace" | "Research Library" | "Settings";
type Workflow = "digital" | "listicles";
type AnalyzedArticle = { url: string; analysis: AnyObj };

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

function Spinner({ size = 16 }: { size?: number }) {
  return <Loader2 className="animate-spin" size={size} />;
}

function MetricCard({ label, value, icon }: { label: string; value: number; icon: ReactNode }) {
  return (
    <div className="metric-card">
      <div className="metric-icon">{icon}</div>
      <div>
        <div className="metric-value">{value}</div>
        <div className="metric-label">{label}</div>
      </div>
    </div>
  );
}

function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return <div className={`note ${tone === "warn" ? "note-warn" : "note-info"}`}>{children}</div>;
}

function PageHeading({
  badge,
  title,
  subtitle,
  action,
}: {
  badge: string;
  title: string;
  subtitle: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <div className="page-badge">{badge}</div>
        <h1 className="page-title">{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

export default function Home() {
  const [nav, setNav] = useState<Nav>("Workspace");
  const [workflow, setWorkflow] = useState<Workflow>("digital");
  const [digitalStep, setDigitalStep] = useState<DigitalStep>("Article");
  const [listicleStep, setListicleStep] = useState<ListicleStep>("Search");
  const [retryMsg, setRetryMsg] = useState<string | null>(null);

  // Analyze state
  const [urlInputs, setUrlInputs] = useState<string[]>([""]);
  const [loadingAnalyze, setLoadingAnalyze] = useState(false);
  const [analyses, setAnalyses] = useState<AnalyzedArticle[]>([]);
  const [activeUrl, setActiveUrl] = useState("");
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

  const angleCount = analysis?.pr_angles?.length || 0;
  const oppCount = opportunities?.opportunities?.length || 0;
  const journCount = journalists?.journalists?.length || 0;
  const listCount = listicles?.opportunities?.length || 0;
  const contactCount = contact?.contacts?.length || 0;

  const steps: readonly string[] = workflow === "digital" ? digitalSteps : listicleSteps;
  const activeStep = workflow === "digital" ? digitalStep : listicleStep;

  function goStep(step: string) {
    if (workflow === "digital") {
      setDigitalStep(step as DigitalStep);
    } else {
      setListicleStep(step as ListicleStep);
    }
  }

  function switchWorkflow() {
    setWorkflow(workflow === "digital" ? "listicles" : "digital");
    setNav("Workspace");
  }

  function addUrlInput() {
    setUrlInputs((current) => (current.length >= 5 ? current : [...current, ""]));
  }

  function updateUrlInput(index: number, value: string) {
    setUrlInputs((current) => current.map((item, i) => (i === index ? value : item)));
  }

  function removeUrlInput(index: number) {
    setUrlInputs((current) => {
      if (current.length <= 1) return current;
      return current.filter((_, i) => i !== index);
    });
  }

  function resetAnalysisDownstream() {
    setSelectedAngle(null);
    setOpportunities(null);
    setSelectedOpp(null);
    setJournalists(null);
    setErrOpp(null);
    setErrJourn(null);
    setRetryMsg(null);
  }

  function activateAnalyzedArticle(item: AnalyzedArticle) {
    setAnalysis(item.analysis);
    setActiveUrl(item.url);
    resetAnalysisDownstream();
  }

  async function analyze(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const rawUrls = urlInputs.map((value) => value.trim()).filter(Boolean);
    const seen = new Set<string>();
    const urls = rawUrls.filter((value) => {
      if (seen.has(value)) return false;
      seen.add(value);
      return true;
    });

    if (urls.length === 0) {
      setErrAnalyze("Add at least one article URL.");
      return;
    }
    if (urls.length > 5) {
      setErrAnalyze(`Analyze up to 5 articles at a time. You entered ${urls.length}.`);
      return;
    }
    const invalid = urls.filter((value) => !value.startsWith("https://"));
    if (invalid.length > 0) {
      setErrAnalyze(`Use full HTTPS URLs. Fix: ${invalid.join(", ")}`);
      return;
    }

    setLoadingAnalyze(true);
    setErrAnalyze(null);
    setAnalyses([]);
    setActiveUrl("");
    setAnalysis(null);
    resetAnalysisDownstream();

    const results: AnalyzedArticle[] = [];
    const failures: string[] = [];
    try {
      for (let index = 0; index < urls.length; index += 1) {
        const articleUrl = urls[index];
        setRetryMsg(`Analyzing ${index + 1} of ${urls.length}...`);
        try {
          const data = await callApi("analyze", { article_url: articleUrl }, (attempt) =>
            setRetryMsg(`Analyzing ${index + 1} of ${urls.length} - retry ${attempt}/3...`)
          );
          results.push({ url: articleUrl, analysis: data });
        } catch (err: any) {
          failures.push(`${articleUrl}: ${err?.message || "failed"}`);
        }
      }

      setAnalyses(results);
      if (results.length > 0) {
        setAnalysis(results[0].analysis);
        setActiveUrl(results[0].url);
      }
      if (failures.length > 0) {
        setErrAnalyze(
          `${failures.length} article(s) could not be analyzed. ${failures.join(" | ")}`
        );
      }
    } finally {
      setLoadingAnalyze(false);
      setRetryMsg(null);
    }
  }

  async function researchAngle(angle: AnyObj) {
    setSelectedAngle(angle);
    setLoadingOpp(true);
    setErrOpp(null);
    setOpportunities(null);
    setSelectedOpp(null);
    setJournalists(null);
    setRetryMsg(null);
    try {
      const data = await callApi("opportunities", { angle }, (a) =>
        setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setOpportunities(data);
      setDigitalStep("Opportunities");
    } catch (err: any) {
      setErrOpp(err?.message || "Something went wrong");
    } finally {
      setLoadingOpp(false);
      setRetryMsg(null);
    }
  }

  async function runOpportunities() {
    if (!selectedAngle) return;
    setLoadingOpp(true);
    setErrOpp(null);
    setOpportunities(null);
    setRetryMsg(null);
    try {
      const data = await callApi("opportunities", { angle: selectedAngle }, (a) =>
        setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setOpportunities(data);
    } catch (err: any) {
      setErrOpp(err?.message || "Something went wrong");
    } finally {
      setLoadingOpp(false);
      setRetryMsg(null);
    }
  }

  async function researchJournalistsFor(opportunity: AnyObj) {
    if (!selectedAngle) return;
    setSelectedOpp(opportunity);
    setJournalists(null);
    setDigitalStep("Journalists");
    setLoadingJourn(true);
    setErrJourn(null);
    setRetryMsg(null);
    try {
      const data = await callApi(
        "journalists",
        { angle: selectedAngle, opportunity },
        (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setJournalists(data);
    } catch (err: any) {
      setErrJourn(err?.message || "Something went wrong");
    } finally {
      setLoadingJourn(false);
      setRetryMsg(null);
    }
  }

  async function runJournalists() {
    if (!selectedAngle || !selectedOpp) return;
    setLoadingJourn(true);
    setErrJourn(null);
    setJournalists(null);
    setRetryMsg(null);
    try {
      const data = await callApi(
        "journalists",
        { angle: selectedAngle, opportunity: selectedOpp },
        (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setJournalists(data);
    } catch (err: any) {
      setErrJourn(err?.message || "Something went wrong");
    } finally {
      setLoadingJourn(false);
      setRetryMsg(null);
    }
  }

  async function runListicles(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!listForm.search_theme.trim()) return;
    setLoadingList(true);
    setErrList(null);
    setListicles(null);
    setSelectedItem(null);
    setContact(null);
    setPolicy(null);
    setRetryMsg(null);
    try {
      const data = await callApi(
        "listicles",
        {
          search_theme: listForm.search_theme.trim(),
          related_queries: listForm.related_queries,
          target_audience: listForm.target_audience,
          target_market: listForm.target_market,
          competitors: listForm.competitors
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          max_results: Number(listForm.max_results) || 8,
        },
        (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setListicles(data);
      setListicleStep("Prospects");
    } catch (err: any) {
      setErrList(err?.message || "Something went wrong");
    } finally {
      setLoadingList(false);
      setRetryMsg(null);
    }
  }

  async function runContact(item: AnyObj) {
    setSelectedItem(item);
    setLoadingContact(true);
    setErrContact(null);
    setContact(null);
    setRetryMsg(null);
    try {
      const data = await callApi("listicle-contact", { item }, (a) =>
        setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
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
    setLoadingPolicy(true);
    setErrPolicy(null);
    setPolicy(null);
    setRetryMsg(null);
    try {
      const data = await callApi("publisher-policy", { item }, (a) =>
        setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setPolicy(data);
    } catch (err: any) {
      setErrPolicy(err?.message || "Something went wrong");
    } finally {
      setLoadingPolicy(false);
      setRetryMsg(null);
    }
  }

  const sidebar = (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">PR</div>
        <div>
          <div className="brand-name">PR Research Agent</div>
          <div className="brand-tagline">Digital PR · Listicles · Drafts</div>
        </div>
      </div>

      <div className="brand-chip">
        <span className="dot" />
        <span>
          Working for <strong>Vista Social</strong>
        </span>
      </div>

      <nav className="sidebar-nav" aria-label="Primary navigation">
        <button className={`nav-item ${nav === "Workspace" ? "active" : ""}`} onClick={() => setNav("Workspace")}>
          <LayoutGrid className="nav-icon" size={17} />
          Workspace
        </button>
        <button
          className={`nav-item ${nav === "Research Library" ? "active" : ""}`}
          onClick={() => setNav("Research Library")}
        >
          <BookOpen className="nav-icon" size={17} />
          Research Library
        </button>
        <button className={`nav-item ${nav === "Settings" ? "active" : ""}`} onClick={() => setNav("Settings")}>
          <SlidersHorizontal className="nav-icon" size={17} />
          Settings
        </button>
      </nav>

      <div className="sidebar-divider" />

      <div className="sidebar-meta">
        <div>
          Model: <strong>gpt-5-nano</strong>
        </div>
        <div>
          Search context: <strong>low</strong>
        </div>
        <div className="sidebar-note">Vercel demo · no automatic outreach</div>
      </div>
    </aside>
  );

  return (
    <div className="app-shell">
      {sidebar}
      <main className="main">
        <div className="content">
          {nav === "Workspace" && (
            <>
              <PageHeading
                badge="Workspace"
                title={workflow === "digital" ? "Digital PR" : "Listicles"}
                subtitle="You approve every decision and every send."
                action={
                  <button className="btn-secondary" onClick={switchWorkflow}>
                    Switch workflow
                  </button>
                }
              />

              <div className="stepper" role="tablist" aria-label="Workflow steps">
                {steps.map((step) => (
                  <button
                    key={step}
                    role="tab"
                    aria-selected={activeStep === step}
                    className={activeStep === step ? "active" : ""}
                    onClick={() => goStep(step)}
                  >
                    {step}
                  </button>
                ))}
              </div>

              {retryMsg && <Note>{retryMsg}</Note>}

              {workflow === "digital" && digitalStep === "Article" && (
                <div className="stack">
                  <section className="card">
                    <h2 className="section-title">Analyze articles</h2>
                    <p className="body-text">
                      Add up to 5 published article URLs. Use the plus button to add another field. The agent extracts
                      the strongest PR angles, the evidence behind them, and the next useful action for each.
                    </p>
                    <form onSubmit={analyze} style={{ marginTop: 16 }}>
                      <div className="stack-sm">
                        {urlInputs.map((value, index) => (
                          <div
                            key={index}
                            style={{ display: "flex", gap: 8, alignItems: "center" }}
                          >
                            <input
                              type="url"
                              value={value}
                              onChange={(e) => updateUrlInput(index, e.target.value)}
                              placeholder={`https://example.com/article-${index + 1}`}
                              className="input"
                            />
                            {urlInputs.length > 1 && (
                              <button
                                type="button"
                                className="btn-secondary"
                                onClick={() => removeUrlInput(index)}
                                aria-label={`Remove article URL ${index + 1}`}
                                title="Remove URL"
                              >
                                <X size={16} />
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                      <div className="actions" style={{ marginTop: 10 }}>
                        {urlInputs.length < 5 && (
                          <button type="button" className="btn-secondary" onClick={addUrlInput}>
                            <Plus size={16} /> Add URL
                          </button>
                        )}
                        {urlInputs.length >= 5 && <span className="meta">Maximum 5 URLs.</span>}
                        <button type="submit" disabled={loadingAnalyze} className="btn-primary">
                          {loadingAnalyze ? <Spinner /> : <Search size={17} />}
                          {loadingAnalyze ? "Analyzing articles..." : "Analyze articles"}
                        </button>
                      </div>
                    </form>
                    <p className="meta" style={{ marginTop: 8 }}>
                      Each new URL runs one analysis call. Up to 5 calls per batch.
                    </p>
                    {errAnalyze && <Note tone="warn">{errAnalyze}</Note>}
                  </section>

                  {analyses.length > 1 && (
                    <section className="card">
                      <h2 className="section-title">Analyzed articles ({analyses.length})</h2>
                      <div className="stack-sm">
                        {analyses.map((item) => (
                          <div key={item.url} className="context-card">
                            <div className="context-label">
                              {activeUrl === item.url ? "Active article" : "Saved analysis"}
                            </div>
                            <div className="context-value">{item.analysis.article_title}</div>
                            <p className="meta">{item.url}</p>
                            {activeUrl !== item.url && (
                              <button
                                type="button"
                                className="btn-secondary"
                                onClick={() => activateAnalyzedArticle(item)}
                              >
                                Use this article
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {analysis && (
                    <section className="card">
                      <h2 className="section-title">{analysis.article_title}</h2>
                      {activeUrl && <p className="meta">{activeUrl}</p>}
                      <p className="meta">{analysis.main_topic}</p>
                      <p className="body-text">{analysis.assessment}</p>
                      {analysis.statistics?.length > 0 && (
                        <>
                          <div className="divider" />
                          <div className="stack-sm">
                            <div className="context-label">Statistics found</div>
                            {analysis.statistics.map((s: AnyObj, i: number) => (
                              <p key={i} className="result-copy">
                                <strong>{s.statistic}</strong> — {s.source} ({s.data_provenance})
                              </p>
                            ))}
                          </div>
                        </>
                      )}
                      <div className="actions">
                        <button className="btn-primary" onClick={() => setDigitalStep("PR angles")}>
                          View PR angles <ArrowRight size={16} />
                        </button>
                      </div>
                    </section>
                  )}
                </div>
              )}

              {workflow === "digital" && digitalStep === "PR angles" && (
                <>
                  <p className="step-caption">
                    Choose the angle with the clearest editorial value. Research is only run for the angle you pick.
                  </p>
                  {!analysis ? (
                    <div className="card empty-state">
                      <h2 className="empty-title">Analyze an article first</h2>
                      <p className="empty-copy">
                        PR angles are built from the article's claims, statistics, and the brand's credible contribution.
                      </p>
                      <button className="btn-secondary" onClick={() => setDigitalStep("Article")}>
                        Go to Article
                      </button>
                    </div>
                  ) : (
                    <div className="stack">
                      {errOpp && <Note tone="warn">{errOpp}</Note>}
                      {(analysis.pr_angles ?? []).map((a: AnyObj, i: number) => (
                        <article className="card" key={`${a.angle}-${i}`}>
                          <h2 className="angle-title">
                            {i + 1}. {a.angle}
                          </h2>
                          <p className="meta">
                            {a.story_type} · {a.recommended_tactic} · Confidence: {a.confidence}
                          </p>
                          <p className="body-text">{a.story_hypothesis}</p>
                          <p className="body-text">
                            <strong>Why a publication might care:</strong> {a.why_useful}
                          </p>

                          <details className="plan">
                            <summary>Full action plan</summary>
                            <div className="plan-body">
                              <p>
                                <strong>Brand contribution:</strong> {a.brand_contribution}
                              </p>
                              <p>
                                <strong>Target publication types:</strong>{" "}
                                {(a.target_publication_types ?? []).join(", ") || "Not specified"}
                              </p>
                              <p>
                                <strong>Journalist beats:</strong>{" "}
                                {(a.target_journalist_beats ?? []).join(", ") || "Not specified"}
                              </p>
                              <p>
                                <strong>Relevant asset:</strong> {a.relevant_asset}
                              </p>
                              <p>
                                <strong>Evidence:</strong> {a.evidence}
                              </p>
                              <p>
                                <strong>Next action:</strong> {a.next_action}
                              </p>
                            </div>
                          </details>

                          <div className="actions">
                            <button
                              className="btn-primary w-full"
                              disabled={loadingOpp}
                              onClick={() => researchAngle(a)}
                            >
                              {loadingOpp && selectedAngle?.angle === a.angle ? (
                                <>
                                  <Spinner /> Researching angle...
                                </>
                              ) : (
                                <>
                                  Research this angle <ArrowRight size={16} />
                                </>
                              )}
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </>
              )}

              {workflow === "digital" && digitalStep === "Opportunities" && (
                <>
                  <p className="step-caption">
                    Research finds existing articles where this angle can add evidence, a useful perspective, or a
                    missing product category.
                  </p>
                  {!selectedAngle ? (
                    <div className="card empty-state">
                      <h2 className="empty-title">Pick a PR angle first</h2>
                      <button className="btn-secondary" onClick={() => setDigitalStep("PR angles")}>
                        Go to PR angles
                      </button>
                    </div>
                  ) : (
                    <div className="stack">
                      <section className="context-card">
                        <span className="context-label">Selected angle</span>
                        <span className="context-value">{selectedAngle.angle}</span>
                      </section>

                      <div className="actions-between">
                        <button className="btn-primary" onClick={runOpportunities} disabled={loadingOpp}>
                          {loadingOpp ? <Spinner /> : <Search size={17} />}
                          {opportunities ? "Run research again" : "Run opportunity research"}
                        </button>
                      </div>

                      {errOpp && <Note tone="warn">{errOpp}</Note>}

                      {opportunities && (
                        <>
                          <p className="step-caption">{opportunities.research_summary}</p>
                          {(opportunities.opportunities ?? []).map((o: AnyObj, i: number) => (
                            <article className="card" key={`${o.article_url}-${i}`}>
                              <div className="card-head">
                                <div>
                                  <h2 className="card-title">{o.article_title}</h2>
                                  <p className="meta">
                                    {o.publication} · {o.published_date} · {o.opportunity_type}
                                  </p>
                                </div>
                                {o.article_url?.startsWith("https://") && (
                                  <a className="btn-secondary" href={o.article_url} target="_blank" rel="noreferrer">
                                    Open article <ExternalLink size={15} />
                                  </a>
                                )}
                              </div>
                              <p className="body-text">
                                <strong>Why relevant:</strong> {o.why_relevant}
                              </p>
                              <p className="body-text">
                                <strong>Brand contribution:</strong> {o.brand_contribution}
                              </p>

                              <details className="plan">
                                <summary>Full opportunity details</summary>
                                <div className="plan-body">
                                  <p>
                                    <strong>Topical relevance:</strong> {o.topical_relevance}
                                  </p>
                                  <p>
                                    <strong>Editorial fit:</strong> {o.editorial_fit}
                                  </p>
                                  <p>
                                    <strong>Competitor mention:</strong> {o.competitor_mention}
                                  </p>
                                  <p>
                                    <strong>Evidence:</strong> {o.evidence}
                                  </p>
                                  <p>
                                    <strong>Recommended action:</strong> {o.recommended_action}
                                  </p>
                                  <p>
                                    <strong>Confidence:</strong> {o.confidence}
                                  </p>
                                </div>
                              </details>

                              <div className="actions">
                                <button
                                  className="btn-primary"
                                  onClick={() => researchJournalistsFor(o)}
                                  disabled={loadingJourn}
                                >
                                  {loadingJourn && selectedOpp?.article_url === o.article_url ? (
                                    <>
                                      <Spinner /> Researching writers...
                                    </>
                                  ) : (
                                    <>
                                      Research journalists <ArrowRight size={16} />
                                    </>
                                  )}
                                </button>
                              </div>
                            </article>
                          ))}
                          {(!opportunities.opportunities || opportunities.opportunities.length === 0) && (
                            <Note tone="warn">No suitable opportunity was verified for this angle.</Note>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </>
              )}

              {workflow === "digital" && digitalStep === "Journalists" && (
                <>
                  <p className="step-caption">
                    Find writers who have covered this topic and could use the brand's contribution.
                  </p>
                  {!selectedAngle || !selectedOpp ? (
                    <div className="card empty-state">
                      <h2 className="empty-title">Pick an opportunity first</h2>
                      <button className="btn-secondary" onClick={() => setDigitalStep("Opportunities")}>
                        Go to Opportunities
                      </button>
                    </div>
                  ) : (
                    <div className="stack">
                      <section className="context-card">
                        <span className="context-label">Selected opportunity</span>
                        <span className="context-value">
                          {selectedOpp.article_title} · {selectedOpp.publication}
                        </span>
                      </section>

                      <div className="actions-between">
                        <button className="btn-primary" onClick={runJournalists} disabled={loadingJourn}>
                          {loadingJourn ? <Spinner /> : <Users size={17} />}
                          {journalists ? "Run research again" : "Run journalist research"}
                        </button>
                      </div>

                      {errJourn && <Note tone="warn">{errJourn}</Note>}

                      {journalists && (
                        <>
                          <p className="step-caption">{journalists.research_summary}</p>
                          {(journalists.journalists ?? []).map((j: AnyObj, i: number) => (
                            <article className="card" key={`${j.name}-${i}`}>
                              <h2 className="card-title">
                                {i + 1}. {j.name}
                              </h2>
                              <p className="meta">
                                {j.publication} · {j.current_role} · Coverage date: {j.article_date} · Confidence:{" "}
                                {j.confidence}
                              </p>
                              <p className="body-text">
                                <strong>Why relevant:</strong> {j.why_relevant}
                              </p>

                              <details className="plan">
                                <summary>Coverage and pitch angle</summary>
                                <div className="plan-body">
                                  <p>
                                    <strong>Relevant article:</strong> {j.relevant_article_title}
                                  </p>
                                  {j.relevant_article_url?.startsWith("https://") && (
                                    <p>
                                      <a href={j.relevant_article_url} target="_blank" rel="noreferrer">
                                        Open coverage <ExternalLink size={13} className="inline" />
                                      </a>
                                    </p>
                                  )}
                                  <p>
                                    <strong>Topic covered:</strong> {j.topic_covered}
                                  </p>
                                  <p>
                                    <strong>Suggested pitch angle:</strong> {j.suggested_pitch_angle}
                                  </p>
                                  <p>
                                    <strong>Profile or contact page:</strong>{" "}
                                    {j.author_profile_or_contact_page}
                                  </p>
                                  <p>
                                    <strong>Evidence:</strong> {j.evidence}
                                  </p>
                                </div>
                              </details>
                            </article>
                          ))}
                          {(!journalists.journalists || journalists.journalists.length === 0) && (
                            <Note tone="warn">
                              No suitable journalist could be verified. Do not guess a contact.
                            </Note>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </>
              )}

              {workflow === "digital" && digitalStep === "Outreach" && (
                <div className="card empty-state">
                  <div className="page-badge">Human approval</div>
                  <h2 className="empty-title">Draft generation is in the local app</h2>
                  <p className="empty-copy">
                    The Vercel demo stops at verified research. The full Streamlit app prepares personalized pitches
                    for review, with editable subject lines, message bodies, and manual status tracking. Nothing is
                    sent automatically.
                  </p>
                  <button className="btn-secondary" onClick={() => setDigitalStep("Journalists")}>
                    Back to Journalists
                  </button>
                </div>
              )}

              {workflow === "listicles" && listicleStep === "Search" && (
                <div className="stack">
                  <section className="card">
                    <h2 className="section-title">Search listicle opportunities</h2>
                    <p className="body-text">
                      Find existing roundups and tools lists where the brand could be considered. Contact and policy
                      research run only when you ask for them.
                    </p>
                    <form onSubmit={runListicles}>
                      <div className="form-grid">
                        <div className="field">
                          <label htmlFor="search-theme">Search theme *</label>
                          <input
                            id="search-theme"
                            required
                            value={listForm.search_theme}
                            onChange={(e) => setListForm({ ...listForm, search_theme: e.target.value })}
                            placeholder="social media management tools"
                            className="input"
                          />
                        </div>
                        <div className="field">
                          <label htmlFor="related-queries">Related queries</label>
                          <input
                            id="related-queries"
                            value={listForm.related_queries}
                            onChange={(e) => setListForm({ ...listForm, related_queries: e.target.value })}
                            placeholder="best social media tools, social media schedulers"
                            className="input"
                          />
                        </div>
                        <div className="field">
                          <label htmlFor="target-audience">Target audience</label>
                          <input
                            id="target-audience"
                            value={listForm.target_audience}
                            onChange={(e) => setListForm({ ...listForm, target_audience: e.target.value })}
                            className="input"
                          />
                        </div>
                        <div className="field">
                          <label htmlFor="target-market">Target market</label>
                          <input
                            id="target-market"
                            value={listForm.target_market}
                            onChange={(e) => setListForm({ ...listForm, target_market: e.target.value })}
                            className="input"
                          />
                        </div>
                        <div className="field">
                          <label htmlFor="competitors">Competitors (comma-separated)</label>
                          <input
                            id="competitors"
                            value={listForm.competitors}
                            onChange={(e) => setListForm({ ...listForm, competitors: e.target.value })}
                            className="input"
                          />
                        </div>
                        <div className="field">
                          <label htmlFor="max-results">Max results</label>
                          <input
                            id="max-results"
                            type="number"
                            min={3}
                            max={10}
                            value={listForm.max_results}
                            onChange={(e) => setListForm({ ...listForm, max_results: Number(e.target.value) })}
                            className="input"
                          />
                          <span className="field-note">Between 3 and 10 verified candidates.</span>
                        </div>
                      </div>
                      <div className="actions">
                        <button type="submit" disabled={loadingList} className="btn-primary">
                          {loadingList ? <Spinner /> : <List size={17} />}
                          Search listicles
                        </button>
                      </div>
                    </form>
                    {errList && <Note tone="warn">{errList}</Note>}
                  </section>

                  {listicles && (
                    <section className="card">
                      <h2 className="section-title">Search result</h2>
                      <p className="body-text">{listicles.research_summary}</p>
                      <div className="actions">
                        <button className="btn-secondary" onClick={() => setListicleStep("Prospects")}>
                          View prospects <ArrowRight size={16} />
                        </button>
                      </div>
                    </section>
                  )}
                </div>
              )}

              {workflow === "listicles" && listicleStep === "Prospects" && (
                <>
                  <p className="step-caption">
                    Review the listicle, its current inclusion status, and the publisher's documented route before
                    preparing any outreach.
                  </p>
                  {!listicles ? (
                    <div className="card empty-state">
                      <h2 className="empty-title">Search for listicles first</h2>
                      <button className="btn-secondary" onClick={() => setListicleStep("Search")}>
                        Go to Search
                      </button>
                    </div>
                  ) : (
                    <div className="stack">
                      <p className="step-caption">{listicles.research_summary}</p>
                      {(listicles.opportunities ?? []).map((item: AnyObj, i: number) => (
                        <article className="card" key={`${item.listicle_url}-${i}`}>
                          <div className="card-head">
                            <div>
                              <h2 className="card-title">{item.listicle_title}</h2>
                              <p className="meta">
                                {item.publication} · {item.placement_type} · {item.published_or_updated}
                              </p>
                            </div>
                            {item.listicle_url?.startsWith("https://") && (
                              <a className="btn-secondary" href={item.listicle_url} target="_blank" rel="noreferrer">
                                Open page <ExternalLink size={15} />
                              </a>
                            )}
                          </div>
                          <p className="body-text">
                            <strong>Fit:</strong> {item.brand_fit}
                          </p>
                          <p className="body-text">
                            <strong>Currently lists brand:</strong> {item.brand_currently_listed}
                          </p>

                          <details className="plan">
                            <summary>Full prospect details</summary>
                            <div className="plan-body">
                              <p>
                                <strong>Category:</strong> {item.listicle_category}
                              </p>
                              <p>
                                <strong>Audience:</strong> {item.target_audience}
                              </p>
                              <p>
                                <strong>Competitors listed:</strong>{" "}
                                {(item.competitors_listed ?? []).join(", ") || "None identified"}
                              </p>
                              <p>
                                <strong>Inclusion gap:</strong> {item.inclusion_gap}
                              </p>
                              <p>
                                <strong>Contact route:</strong> {item.contact_route}
                              </p>
                              <p>
                                <strong>Evidence:</strong> {item.evidence}
                              </p>
                              <p>
                                <strong>Recommended action:</strong> {item.recommended_action}
                              </p>
                              <p>
                                <strong>Confidence:</strong> {item.confidence}
                              </p>
                            </div>
                          </details>

                          <div className="actions">
                            <button
                              className="btn-secondary"
                              onClick={() => runContact(item)}
                              disabled={loadingContact}
                            >
                              {loadingContact && selectedItem === item ? <Spinner /> : <Mail size={16} />}
                              Find contact
                            </button>
                            <button
                              className="btn-secondary"
                              onClick={() => runPolicy(item)}
                              disabled={loadingPolicy}
                            >
                              {loadingPolicy && selectedItem === item ? <Spinner /> : <Shield size={16} />}
                              Check policy
                            </button>
                          </div>

                          {selectedItem === item &&
                            (loadingContact ||
                              loadingPolicy ||
                              contact ||
                              policy ||
                              errContact ||
                              errPolicy) && (
                              <div className="inline-panel">
                                {errContact && <Note tone="warn">{errContact}</Note>}
                                {loadingContact && (
                                  <p className="result-copy">
                                    <Spinner /> Researching contact route...
                                  </p>
                                )}
                                {contact && (
                                  <div className="result-block">
                                    <h3 className="result-title">Contact research</h3>
                                    <p className="result-meta">{contact.research_summary}</p>
                                    {(contact.contacts ?? []).map((c: AnyObj, ci: number) => (
                                      <div key={`${c.contact_name}-${ci}`} className="result-block">
                                        <p className="result-copy">
                                          <strong>{c.contact_name}</strong> — {c.current_role}
                                        </p>
                                        <p className="result-copy">
                                          <strong>Email:</strong> {c.professional_email}
                                        </p>
                                        <p className="result-copy">
                                          <strong>Method:</strong> {c.contact_method}
                                        </p>
                                        <p className="result-copy">{c.why_this_contact}</p>
                                        <p className="result-meta">Confidence: {c.confidence}</p>
                                        {c.source_url && c.source_url !== "Unknown" && (
                                          <a href={c.source_url} target="_blank" rel="noreferrer">
                                            Open source <ExternalLink size={13} className="inline" />
                                          </a>
                                        )}
                                      </div>
                                    ))}
                                    {(!contact.contacts || contact.contacts.length === 0) && (
                                      <p className="result-copy">No verified contact found.</p>
                                    )}
                                  </div>
                                )}

                                {errPolicy && <Note tone="warn">{errPolicy}</Note>}
                                {loadingPolicy && (
                                  <p className="result-copy">
                                    <Spinner /> Checking publisher policy...
                                  </p>
                                )}
                                {policy && (
                                  <div className="result-block">
                                    <h3 className="result-title">Publisher policy</h3>
                                    <p className="result-copy">
                                      <strong>Status:</strong> {policy.policy_status}
                                    </p>
                                    <p className="result-copy">
                                      <strong>Disposition:</strong> {policy.recommended_disposition}
                                    </p>
                                    <p className="result-copy">{policy.policy_summary}</p>
                                    <p className="result-copy">
                                      <strong>Reason:</strong> {policy.disposition_reason}
                                    </p>
                                    <p className="result-copy">
                                      <strong>Route:</strong> {policy.recommended_route}
                                    </p>
                                    <p className="result-meta">Confidence: {policy.confidence}</p>
                                    {policy.policy_source_url && policy.policy_source_url !== "Unknown" && (
                                      <a href={policy.policy_source_url} target="_blank" rel="noreferrer">
                                        Open policy source <ExternalLink size={13} className="inline" />
                                      </a>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                        </article>
                      ))}
                      {(!listicles.opportunities || listicles.opportunities.length === 0) && (
                        <Note tone="warn">No listicle candidates were verified for this search.</Note>
                      )}
                    </div>
                  )}
                </>
              )}

              {workflow === "listicles" && listicleStep === "Outreach" && (
                <div className="card empty-state">
                  <div className="page-badge">Human approval</div>
                  <h2 className="empty-title">Inclusion requests are in the local app</h2>
                  <p className="empty-copy">
                    The Vercel demo stops at verified prospects, contacts, and publisher policies. The full Streamlit
                    app prepares listicle inclusion requests for manual review. Nothing is sent or submitted
                    automatically.
                  </p>
                  <button className="btn-secondary" onClick={() => setListicleStep("Prospects")}>
                    Back to Prospects
                  </button>
                </div>
              )}
            </>
          )}

          {nav === "Research Library" && (
            <>
              <PageHeading
                badge="Research Library"
                title="Research Library"
                subtitle="Everything researched in this browser session."
                action={
                  <button className="btn-secondary" onClick={() => setNav("Workspace")}>
                    Back to Workspace
                  </button>
                }
              />
              <div className="metric-grid">
                <MetricCard label="PR angles" value={angleCount} icon={<BarChart3 size={20} />} />
                <MetricCard label="PR opportunities" value={oppCount} icon={<FileText size={20} />} />
                <MetricCard label="Journalists" value={journCount} icon={<Users size={20} />} />
                <MetricCard label="Listicle candidates" value={listCount} icon={<List size={20} />} />
                <MetricCard label="Contacts found" value={contactCount} icon={<Mail size={20} />} />
                <MetricCard label="Policies checked" value={policy ? 1 : 0} icon={<Shield size={20} />} />
              </div>

              <div className="library-grid">
                <section className="card">
                  <h2 className="section-title">Digital PR</h2>
                  <p className="body-text">
                    {analysis ? analysis.article_title : "No article analyzed in this session yet."}
                  </p>
                  <p className="meta">
                    {opportunities
                      ? `${oppCount} opportunities · ${journCount} journalists`
                      : "Run an article analysis to start the Digital PR workflow."}
                  </p>
                  <div className="actions">
                    <button
                      className="btn-secondary"
                      onClick={() => {
                        setWorkflow("digital");
                        setDigitalStep(analysis ? "PR angles" : "Article");
                        setNav("Workspace");
                      }}
                    >
                      Open Digital PR
                    </button>
                  </div>
                </section>

                <section className="card">
                  <h2 className="section-title">Listicles</h2>
                  <p className="body-text">
                    {listicles ? listicles.search_theme : "No listicle search in this session yet."}
                  </p>
                  <p className="meta">
                    {listicles
                      ? `${listCount} candidates · ${contactCount} contacts`
                      : "Search for roundups and tools lists to start."}
                  </p>
                  <div className="actions">
                    <button
                      className="btn-secondary"
                      onClick={() => {
                        setWorkflow("listicles");
                        setListicleStep(listicles ? "Prospects" : "Search");
                        setNav("Workspace");
                      }}
                    >
                      Open Listicles
                    </button>
                  </div>
                </section>
              </div>

              <Note>
                Saved libraries, CSV exports, backups, and draft history live in the full local Streamlit app. This
                Vercel demo keeps research in the current browser session only.
              </Note>
            </>
          )}

          {nav === "Settings" && (
            <>
              <PageHeading
                badge="Settings"
                title="Settings"
                subtitle="Read-only in the Vercel demo. The local app stores these settings persistently."
                action={
                  <button className="btn-secondary" onClick={() => setNav("Workspace")}>
                    Back to Workspace
                  </button>
                }
              />
              <div className="stack">
                <section className="card">
                  <h2 className="section-title">Brand and model</h2>
                  <div className="setting-row">
                    <span>Brand</span>
                    <strong>Vista Social</strong>
                  </div>
                  <div className="setting-row">
                    <span>Sender name</span>
                    <strong>Prachi</strong>
                  </div>
                  <div className="setting-row">
                    <span>Job role</span>
                    <strong>SEO Specialist</strong>
                  </div>
                  <div className="setting-row">
                    <span>Model</span>
                    <strong>gpt-5-nano</strong>
                  </div>
                  <div className="setting-row">
                    <span>Search context</span>
                    <strong>low</strong>
                  </div>
                  <div className="setting-row">
                    <span>Data storage</span>
                    <strong>Browser session only</strong>
                  </div>
                  <div className="setting-row">
                    <span>Outreach</span>
                    <strong>Human approval required</strong>
                  </div>
                </section>

                <section className="card">
                  <h2 className="section-title">Safety</h2>
                  <p className="body-text">
                    The app never sends email, submits forms, or contacts publishers. Research is only run when you
                    click an action. The OpenAI API key stays on the server and is never sent to the browser.
                  </p>
                </section>

                <Note>
                  This Vercel build is a Next.js port of the local Streamlit tool. It calls the same research API, but
                  accounts, saved libraries, CSV exports, backups, and draft generation are available only in the local
                  app.
                </Note>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
