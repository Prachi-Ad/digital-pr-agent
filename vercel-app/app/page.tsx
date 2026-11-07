"use client";

import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Copy,
  Download,
  ExternalLink,
  FileText,
  KeyRound,
  LayoutGrid,
  List,
  Loader2,
  Mail,
  Plus,
  RefreshCw,
  Search,
  Server,
  Shield,
  SlidersHorizontal,
  Users,
  X,
} from "lucide-react";

type AnyObj = Record<string, any>;

const digitalPhases = ["Research", "Prospects", "Outreach"] as const;
const listiclePhases = ["Find & review", "Outreach"] as const;
type DigitalPhase = (typeof digitalPhases)[number];
type ListiclePhase = (typeof listiclePhases)[number];

const digitalSteps = ["Article", "PR angles", "Opportunities", "Journalists", "Outreach"] as const;
const listicleSteps = ["Search", "Prospects", "Outreach"] as const;
type DigitalStep = (typeof digitalSteps)[number];
type ListicleStep = (typeof listicleSteps)[number];

const phaseOfDigitalStep: Record<DigitalStep, DigitalPhase> = {
  Article: "Research",
  "PR angles": "Research",
  Opportunities: "Prospects",
  Journalists: "Prospects",
  Outreach: "Outreach",
};
const firstStepOfDigitalPhase: Record<DigitalPhase, DigitalStep> = {
  Research: "Article",
  Prospects: "Opportunities",
  Outreach: "Outreach",
};
const phaseOfListicleStep: Record<ListicleStep, ListiclePhase> = {
  Search: "Find & review",
  Prospects: "Find & review",
  Outreach: "Outreach",
};
const firstStepOfListiclePhase: Record<ListiclePhase, ListicleStep> = {
  "Find & review": "Search",
  Outreach: "Outreach",
};
const phaseCopy: Record<string, string> = {
  Research: "Analyze the article and pick the angle. The evidence stays on screen.",
  Prospects: "Review the editorial openings. Writers appear for each approved one.",
  Outreach: "Draft and approve. The public demo never sends email.",
  "Find & review": "Find pages worth pursuing, then review fit, contact route, and policy.",
};

const fitStyles: Record<string, { className: string; label: string }> = {
  "Strong fit": { className: "fit-good", label: "Good for PR" },
  "Possible fit": { className: "fit-possible", label: "Possible" },
  "Weak fit": { className: "fit-warn", label: "Weak PR fit" },
  "Not suitable": { className: "fit-bad", label: "Not good for PR" },
};

function shortText(value: any, limit = 260) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : `${text.slice(0, limit - 1).replace(/[\s,.;:]+$/, "")}…`;
}
type Nav = "Workspace" | "Research Library" | "Settings";
type Workflow = "digital" | "listicles";
type AnalyzedArticle = { url: string; analysis: AnyObj };
type DemoEmailMethod = "app-password" | "oauth" | "smtp";

const emailMethodOptions: {
  id: DemoEmailMethod;
  label: string;
  status: "Active locally" | "Optional";
  description: string;
  facts: Array<[string, string]>;
  note: string;
  icon: ReactNode;
}[] = [
  {
    id: "app-password",
    label: "Google app password",
    status: "Active locally",
    description: "Personal Gmail app password. This is the method configured in the local sender.",
    facts: [
      ["From account", "Personal Gmail (configured locally)"],
      ["SMTP", "smtp.gmail.com · port 587 · STARTTLS"],
      ["Credentials", "Local, gitignored storage only"],
      ["Login check", "Configured locally · verify in the local app"],
    ],
    note: "A 16-character Google app password is used. A normal Google account password will not work.",
    icon: <KeyRound size={18} />,
  },
  {
    id: "oauth",
    label: "Google Workspace sign-in (OAuth)",
    status: "Optional",
    description: "For Workspace accounts where app passwords are blocked. Requires a Google Cloud client.",
    facts: [
      ["Connection", "Not connected"],
      ["OAuth client", "Not configured"],
      ["Redirect URI", "http://localhost:8501/"],
      ["Scopes", "openid · email · mail.google.com"],
    ],
    note: "A Workspace admin may block the OAuth client or scope. The app reports the error rather than bypassing admin policy.",
    icon: <Shield size={18} />,
  },
  {
    id: "smtp",
    label: "Custom SMTP / designated email",
    status: "Optional",
    description: "For another mailbox with provider-supplied SMTP credentials.",
    facts: [
      ["Connection", "Not configured"],
      ["Security", "STARTTLS or SSL/TLS"],
      ["From address", "Set by the designated mailbox"],
      ["Credentials", "Local, gitignored storage only"],
    ],
    note: "Use this when the mailbox is not Google Workspace or the provider supplies SMTP login details.",
    icon: <Server size={18} />,
  },
];

let demoToken: { token: string; expiresAt: number } | null = null;

async function getDemoToken(force = false): Promise<string> {
  if (!force && demoToken && demoToken.expiresAt > Date.now() + 20_000) {
    return demoToken.token;
  }
  const res = await fetch("/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    // Shared-password gate: send the visitor to sign in, then back here.
    if (typeof window !== "undefined") window.location.href = "/login?next=/";
    throw new Error("Sign in required.");
  }
  if (!res.ok || !data?.token) {
    throw new Error(data?.detail || "Could not start a demo session. Please reload the page.");
  }
  demoToken = {
    token: data.token,
    expiresAt: Date.now() + (Number(data.expiresIn) || 300) * 1000,
  };
  return demoToken.token;
}

async function callApi(action: string, body: any = {}, onRetry?: (attempt: number) => void) {
  const maxAttempts = 3;
  let lastErr: any = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const token = await getDemoToken(attempt > 1);
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ action, ...body }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) return data;

      const message = data?.detail || data?.error || "Request failed";
      if (res.status === 401 || res.status === 403) {
        demoToken = null;
      }
      // Retry auth failures and server faults only. A 400 or 429 will not
      // succeed on a retry, and hammering the endpoint makes rate limits worse.
      const retryable = res.status === 401 || res.status === 403 || res.status >= 500;
      if (!retryable) throw Object.assign(new Error(message), { fatal: true });
      throw new Error(message);
    } catch (err: any) {
      lastErr = err;
      if (err?.fatal) throw err;
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
  const [showStart, setShowStart] = useState(false);
  const [digitalStep, setDigitalStep] = useState<DigitalStep>("Article");
  const [listicleStep, setListicleStep] = useState<ListicleStep>("Search");
  const [retryMsg, setRetryMsg] = useState<string | null>(null);
  const [demoEmailMethod, setDemoEmailMethod] = useState<DemoEmailMethod>("app-password");
  const selectedEmailMethod =
    emailMethodOptions.find((method) => method.id === demoEmailMethod) ?? emailMethodOptions[0];

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
  const [drafts, setDrafts] = useState<Record<string, AnyObj>>({});
  const [loadingDraft, setLoadingDraft] = useState<string | null>(null);
  const [errDraft, setErrDraft] = useState<string | null>(null);

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

  const phases: readonly string[] = workflow === "digital" ? digitalPhases : listiclePhases;
  const activePhase =
    workflow === "digital"
      ? phaseOfDigitalStep[digitalStep]
      : phaseOfListicleStep[listicleStep];

  function goStep(phase: string) {
    if (workflow === "digital") {
      setDigitalStep(firstStepOfDigitalPhase[phase as DigitalPhase]);
    } else {
      setListicleStep(firstStepOfListiclePhase[phase as ListiclePhase]);
    }
  }

  function startNewDigital() {
    setAnalysis(null);
    setAnalyses([]);
    setActiveUrl("");
    resetAnalysisDownstream();
    setShowStart(false);
    setWorkflow("digital");
    setDigitalStep("Article");
  }

  function continueDigital() {
    setShowStart(false);
    setWorkflow("digital");
  }

  function startNewListicles() {
    setListicles(null);
    setShowStart(false);
    setWorkflow("listicles");
    setListicleStep("Search");
  }

  function continueListicles() {
    setShowStart(false);
    setWorkflow("listicles");
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
    setDrafts({});
    setErrOpp(null);
    setErrJourn(null);
    setErrDraft(null);
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

  async function regenerateAnalysis() {
    const targetUrl = activeUrl || analyses[0]?.url;
    if (!targetUrl) {
      setErrAnalyze("Analyze an article first.");
      return;
    }

    setLoadingAnalyze(true);
    setErrAnalyze(null);
    setRetryMsg("Generating a fresh analysis...");
    try {
      const data = await callApi("analyze", { article_url: targetUrl }, (attempt) =>
        setRetryMsg(`Generating again - retry ${attempt}/3...`)
      );
      setAnalyses((current) =>
        current.some((item) => item.url === targetUrl)
          ? current.map((item) => (item.url === targetUrl ? { url: targetUrl, analysis: data } : item))
          : [...current, { url: targetUrl, analysis: data }]
      );
      setAnalysis(data);
      setActiveUrl(targetUrl);
      resetAnalysisDownstream();
    } catch (err: any) {
      setErrAnalyze(err?.message || "Something went wrong");
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
    setDrafts({});
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
    setDrafts({});
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

  async function writeDraft(person: AnyObj) {
    if (!selectedAngle || !selectedOpp) return;
    const key = String(person.name || "contact");
    setLoadingDraft(key);
    setErrDraft(null);
    setRetryMsg(null);
    try {
      const data = await callApi(
        "draft",
        { angle: selectedAngle, opportunity: selectedOpp, person },
        (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setDrafts((current) => ({ ...current, [key]: data }));
      setDigitalStep("Outreach");
    } catch (err: any) {
      setErrDraft(err?.message || "Draft generation failed");
    } finally {
      setLoadingDraft(null);
      setRetryMsg(null);
    }
  }

  function downloadText(filename: string, text: string) {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadCampaignCsv() {
    const opps = opportunities?.opportunities ?? [];
    const people = journalists?.journalists ?? [];
    const header = [
      "publication",
      "site_domain",
      "article_title",
      "article_url",
      "pr_fit",
      "audience_question",
      "aeo_answer",
      "aeo_format",
      "aeo_schema",
      "contact_name",
      "contact_role",
      "subject",
      "body",
    ];
    const rows: string[][] = [];
    for (const opportunity of opps) {
      const selected = selectedOpp?.article_url === opportunity.article_url;
      const contacts = selected && people.length ? people : [null];
      for (const person of contacts) {
        const draft = person ? drafts[String(person.name || "contact")] : null;
        let domain = "";
        try {
          domain = new URL(opportunity.article_url || "").hostname.replace(/^www\./, "");
        } catch {
          domain = "";
        }
        rows.push([
          opportunity.publication || "",
          domain,
          opportunity.article_title || "",
          opportunity.article_url || "",
          opportunity.pr_fit || "",
          opportunity.audience_question || "",
          opportunity.aeo_answer || "",
          opportunity.aeo_format || "",
          opportunity.aeo_schema || "",
          person?.name || "",
          person?.current_role || "",
          draft?.subject_line || "",
          draft?.message_body || "",
        ]);
      }
    }
    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(","))
      .join("\r\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "pr_sites_contacts.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function generateListicles() {
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

  async function runListicles(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    await generateListicles();
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
        <button
          type="button"
          className="btn-secondary"
          onClick={async () => {
            await fetch("/api/logout", { method: "POST", cache: "no-store" });
            window.location.href = "/login";
          }}
        >
          Sign out
        </button>
      </div>
    </aside>
  );

  return (
    <div className="app-shell">
      {sidebar}
      <main className="main">
        <div className="content">
          {nav === "Workspace" && showStart && (
            <div className="stack">
              <PageHeading
                badge="Workspace"
                title="Start a campaign"
                subtitle="One clear path from research to a copy-ready pitch. Nothing is sent."
              />
              <section className="card">
                <h2 className="section-title">Digital PR</h2>
                <p className="body-text">
                  Turn a published article into angles, editorial openings, writer/contact research, and a
                  personalized pitch.
                </p>
                <div className="actions">
                  <button className="btn-primary" onClick={continueDigital}>
                    {analysis ? "Continue Digital PR" : "Start Digital PR"} <ArrowRight size={15} />
                  </button>
                  <button className="btn-secondary" onClick={startNewDigital}>
                    Start new
                  </button>
                </div>
              </section>
              <section className="card">
                <h2 className="section-title">Listicle inclusion</h2>
                <p className="body-text">
                  Find roundups and directories where the product fits, then research the contact and policy.
                </p>
                <div className="actions">
                  <button className="btn-primary" onClick={continueListicles}>
                    {listicles ? "Continue listicles" : "Start listicles"} <ArrowRight size={15} />
                  </button>
                  <button className="btn-secondary" onClick={startNewListicles}>
                    Start new
                  </button>
                </div>
              </section>
            </div>
          )}

          {nav === "Workspace" && !showStart && (
            <>
              <PageHeading
                badge="Workspace"
                title={workflow === "digital" ? "Digital PR" : "Listicles"}
                subtitle={phaseCopy[activePhase] || "You approve every decision and every send."}
                action={
                  <button className="btn-secondary" onClick={() => setShowStart(true)}>
                    ← Back to start
                  </button>
                }
              />

              <div className="stepper" role="tablist" aria-label="Workflow phases">
                {phases.map((phase) => (
                  <button
                    key={phase}
                    role="tab"
                    aria-selected={activePhase === phase}
                    className={activePhase === phase ? "active" : ""}
                    onClick={() => goStep(phase)}
                  >
                    {phase}
                  </button>
                ))}
              </div>
              <p className="meta" style={{ marginTop: 8 }}>
                Phase {phases.indexOf(activePhase) + 1} of {phases.length} · {activePhase}
              </p>

              {retryMsg && <Note>{retryMsg}</Note>}

              {workflow === "digital" && activePhase === "Research" && (
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
                              aria-label={`Article URL ${index + 1}`}
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
                        <button className="btn-secondary" onClick={regenerateAnalysis} disabled={loadingAnalyze}>
                          {loadingAnalyze ? <Spinner /> : <RefreshCw size={16} />}
                          {loadingAnalyze ? "Generating again..." : "Generate again"}
                        </button>
                      </div>
                    </section>
                  )}
                </div>
              )}

              {workflow === "digital" && activePhase === "Research" && !!analysis && (
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
                      <div className="actions-between">
                        <span className="meta">Regenerate the angles from the active article.</span>
                        <button className="btn-secondary" onClick={regenerateAnalysis} disabled={loadingAnalyze}>
                          {loadingAnalyze ? <Spinner /> : <RefreshCw size={16} />}
                          {loadingAnalyze ? "Generating again..." : "Generate again"}
                        </button>
                      </div>
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

              {workflow === "digital" && activePhase === "Prospects" && (
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
                          {loadingOpp ? <Spinner /> : opportunities ? <RefreshCw size={17} /> : <Search size={17} />}
                          {opportunities ? "Generate again" : "Run opportunity research"}
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
                                <strong>Why it matters:</strong> {shortText(o.why_relevant)}
                              </p>
                              <p className="meta">
                                {o.topic} · {o.opportunity_type} · Confidence: {o.confidence}
                              </p>
                              {o.pr_fit && fitStyles[o.pr_fit] && (
                                <div className={`fit-banner ${fitStyles[o.pr_fit].className}`}>
                                  <strong>{fitStyles[o.pr_fit].label}</strong>
                                  <span>{o.pr_fit_reason}</span>
                                </div>
                              )}
                              {Array.isArray(o.pr_red_flags) && o.pr_red_flags.length > 0 && (
                                <p className="meta">Signals: {o.pr_red_flags.join(" · ")}</p>
                              )}

                              {o.audience_question && o.audience_question !== "Not assessed" && (
                                <details className="plan" open>
                                  <summary>AEO angle</summary>
                                  <div className="plan-body">
                                    <p>
                                      <strong>Audience question:</strong> {o.audience_question}
                                    </p>
                                    {o.aeo_answer && (
                                      <p>
                                        <strong>Answer to own:</strong> {o.aeo_answer}
                                      </p>
                                    )}
                                    {o.aeo_format && (
                                      <p>
                                        <strong>Format:</strong> {o.aeo_format}
                                      </p>
                                    )}
                                    {o.aeo_schema && (
                                      <p>
                                        <strong>Schema:</strong> {o.aeo_schema}
                                      </p>
                                    )}
                                  </div>
                                </details>
                              )}

                              <details className="plan">
                                <summary>Full evidence and notes</summary>
                                <div className="plan-body">
                                  <p>
                                    <strong>Why relevant:</strong> {o.why_relevant}
                                  </p>
                                  <p>
                                    <strong>Topic:</strong> {o.topic}
                                  </p>
                                  <p>
                                    <strong>Opportunity type:</strong> {o.opportunity_type}
                                  </p>
                                  <p>
                                    <strong>Brand contribution:</strong> {o.brand_contribution}
                                  </p>
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
                                      Find writers & contacts <ArrowRight size={16} />
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

              {workflow === "digital" && activePhase === "Prospects" && !!selectedOpp && (
                <>
                  <p className="step-caption">
                    Find writers or the best content/SEO contact for this article. If no named writer matches, the publication contact is used instead.
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
                          {loadingJourn ? <Spinner /> : journalists ? <RefreshCw size={17} /> : <Users size={17} />}
                          {journalists ? "Find again" : "Find writers & contacts"}
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

                              <div className="actions">
                                <button
                                  className="btn-primary"
                                  onClick={() => writeDraft(j)}
                                  disabled={loadingDraft === j.name}
                                >
                                  {loadingDraft === j.name ? (
                                    <>
                                      <Spinner /> Writing pitch...
                                    </>
                                  ) : drafts[j.name] ? (
                                    <>
                                      Write again <RefreshCw size={15} />
                                    </>
                                  ) : (
                                    <>
                                      Write pitch <ArrowRight size={15} />
                                    </>
                                  )}
                                </button>
                              </div>
                              {drafts[j.name] && (
                                <p className="meta">Draft ready — open Outreach to copy it.</p>
                              )}
                            </article>
                          ))}
                          {(!journalists.journalists || journalists.journalists.length === 0) && (
                            <Note tone="warn">
                              No writer or contact could be verified. Do not guess one.
                            </Note>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </>
              )}

              {workflow === "digital" && activePhase === "Outreach" && (
                <div className="stack">
                  <div className="actions-between">
                    <p className="step-caption">
                      Personalized drafts for the selected opportunity. Copy or download them; nothing is sent.
                    </p>
                    <button className="btn-secondary" onClick={downloadCampaignCsv}>
                      Download CSV <Download size={15} />
                    </button>
                  </div>

                  {errDraft && <Note tone="warn">{errDraft}</Note>}

                  {Object.keys(drafts).length === 0 ? (
                    <div className="card empty-state">
                      <div className="page-badge">Human approval</div>
                      <h2 className="empty-title">No drafts yet</h2>
                      <p className="empty-copy">
                        Go back to Contacts and click <strong>Write pitch</strong> on a writer or content/SEO contact.
                      </p>
                      <button className="btn-secondary" onClick={() => setDigitalStep("Journalists")}>
                        Back to Contacts
                      </button>
                    </div>
                  ) : (
                    Object.entries(drafts).map(([name, draft]) => (
                      <article className="card" key={name}>
                        <h2 className="card-title">{draft.recipient_name || name}</h2>
                        <p className="meta">
                          {draft.publication} · {draft.recipient_role} · {draft.channel}
                        </p>
                        <p className="body-text">
                          <strong>Subject:</strong> {draft.subject_line}
                        </p>
                        <div className="draft-body">{draft.message_body}</div>
                        {(draft.aeo_question || draft.aeo_answer) && (
                          <details className="plan">
                            <summary>AEO angle used</summary>
                            <div className="plan-body">
                              {draft.aeo_question && (
                                <p>
                                  <strong>Question:</strong> {draft.aeo_question}
                                </p>
                              )}
                              {draft.aeo_answer && (
                                <p>
                                  <strong>Answer:</strong> {draft.aeo_answer}
                                </p>
                              )}
                            </div>
                          </details>
                        )}
                        <div className="actions">
                          <button
                            className="btn-secondary"
                            onClick={() =>
                              navigator.clipboard.writeText(
                                `Subject: ${draft.subject_line}\n\n${draft.message_body}`
                              )
                            }
                          >
                            <Copy size={15} /> Copy email
                          </button>
                          <button
                            className="btn-secondary"
                            onClick={() =>
                              downloadText(
                                `pitch-${(draft.recipient_name || name).replace(/\s+/g, "-").toLowerCase()}.txt`,
                                `Subject: ${draft.subject_line}\n\n${draft.message_body}\n`
                              )
                            }
                          >
                            <Download size={15} /> Download
                          </button>
                        </div>
                        <details className="plan">
                          <summary>Facts to verify</summary>
                          <div className="plan-body">
                            {(draft.facts_to_verify ?? []).length > 0 ? (
                              (draft.facts_to_verify ?? []).map((fact: string, index: number) => (
                                <p key={index}>{fact}</p>
                              ))
                            ) : (
                              <p>None listed. Verify names, links, and claims.</p>
                            )}
                            {draft.compliance_notes && (
                              <p>
                                <strong>Compliance:</strong> {draft.compliance_notes}
                              </p>
                            )}
                            {draft.personalization_evidence && (
                              <p>
                                <strong>Personalization:</strong> {draft.personalization_evidence}
                              </p>
                            )}
                          </div>
                        </details>
                      </article>
                    ))
                  )}
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
                    loadingList ? (
                      <div className="card empty-state">
                        <h2 className="empty-title">Generating fresh listicle prospects...</h2>
                        <p className="meta">The new results will replace the previous search when ready.</p>
                      </div>
                    ) : (
                      <div className="card empty-state">
                        <h2 className="empty-title">Search for listicles first</h2>
                        <button className="btn-secondary" onClick={() => setListicleStep("Search")}>
                          Go to Search
                        </button>
                      </div>
                    )
                  ) : (
                    <div className="stack">
                      <div className="actions-between">
                        <p className="step-caption">{listicles.research_summary}</p>
                        <button
                          className="btn-secondary"
                          onClick={generateListicles}
                          disabled={loadingList || !listForm.search_theme.trim()}
                        >
                          {loadingList ? <Spinner /> : <RefreshCw size={16} />}
                          {loadingList ? "Generating again..." : "Generate again"}
                        </button>
                      </div>
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
                                    <div className="card-head">
                                      <h3 className="result-title">Contact research</h3>
                                      <button
                                        type="button"
                                        className="btn-ghost"
                                        onClick={() => runContact(item)}
                                        disabled={loadingContact}
                                      >
                                        {loadingContact ? <Spinner /> : <RefreshCw size={14} />}
                                        Refresh
                                      </button>
                                    </div>
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
                                    <div className="card-head">
                                      <h3 className="result-title">Publisher policy</h3>
                                      <button
                                        type="button"
                                        className="btn-ghost"
                                        onClick={() => runPolicy(item)}
                                        disabled={loadingPolicy}
                                      >
                                        {loadingPolicy ? <Spinner /> : <RefreshCw size={14} />}
                                        Refresh
                                      </button>
                                    </div>
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
                subtitle="Read-only preview of the local app settings. No credentials are collected and no email can be sent from this demo."
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
                    <span>Sender identity</span>
                    <strong>Prachi, SEO Specialist (fixed)</strong>
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
                    <span>Draft writing</span>
                    <strong>No web search</strong>
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
                  <div className="card-head">
                    <div>
                      <h2 className="section-title">Email sending (designated sender)</h2>
                      <p className="meta">Local-only sender. This demo is a display-only preview.</p>
                    </div>
                    <span className="status-pill">No sending here</span>
                  </div>
                  <p className="body-text">
                    The local Streamlit app sends explicitly approved drafts from the configured Gmail account.
                    Credentials stay in local, gitignored storage. This demo does not collect credentials, connect to
                    Gmail, or send email.
                  </p>

                  <div className="method-grid" aria-label="Email sending methods">
                    {emailMethodOptions.map((method) => (
                      <button
                        key={method.id}
                        type="button"
                        className={`method-card ${demoEmailMethod === method.id ? "active" : ""}`}
                        onClick={() => setDemoEmailMethod(method.id)}
                        aria-pressed={demoEmailMethod === method.id}
                      >
                        <span className="method-icon">{method.icon}</span>
                        <span className="method-copy">
                          <span className="method-topline">
                            <span className="method-name">{method.label}</span>
                            <span
                              className={`status-pill ${method.status === "Active locally" ? "active" : ""}`}
                            >
                              {method.status}
                            </span>
                          </span>
                          <span className="method-note">{method.description}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                  <p className="method-footnote">
                    "Active locally" reflects the local Streamlit app, not this demo. Optional methods are available
                    but unconfigured.
                  </p>

                  <div className="method-preview" role="status" aria-live="polite">
                    <div className="method-preview-head">
                      <div>
                        <h3 className="card-title">{selectedEmailMethod.label}</h3>
                        <p className="meta">
                          Display-only preview. No fields are editable and no credentials are stored here.
                        </p>
                      </div>
                      <span
                        className={`status-pill ${
                          selectedEmailMethod.status === "Active locally" ? "active" : ""
                        }`}
                      >
                        {selectedEmailMethod.status}
                      </span>
                    </div>
                    {selectedEmailMethod.facts.map(([label, value]) => (
                      <div className="setting-row" key={label}>
                        <span>{label}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                    <p className="method-footnote">{selectedEmailMethod.note}</p>
                  </div>

                  <div className="divider" />
                  <h3 className="card-title">Batch safeguards</h3>
                  <div className="setting-row">
                    <span>Human approval</span>
                    <strong>Required for every draft</strong>
                  </div>
                  <div className="setting-row">
                    <span>Batch confirmation</span>
                    <strong>Required before sending</strong>
                  </div>
                  <div className="setting-row">
                    <span>Delay between sends</span>
                    <strong>30 seconds</strong>
                  </div>
                  <div className="setting-row">
                    <span>Daily cap</span>
                    <strong>20 successful sends</strong>
                  </div>
                  <div className="setting-row">
                    <span>Do-not-send list</span>
                    <strong>Blocks matching addresses</strong>
                  </div>
                  <div className="setting-row">
                    <span>Opt-out footer</span>
                    <strong>Added to every email</strong>
                  </div>
                  <div className="setting-row">
                    <span>Audit log</span>
                    <strong>Permanent send history</strong>
                  </div>
                </section>

                <section className="card">
                  <h2 className="section-title">Do-not-send list (opt-outs)</h2>
                  <p className="body-text">
                    If someone asks not to be contacted, add their address in the local app. Matching drafts are
                    blocked from every future batch, and the opt-out footer asks recipients to reply "unsubscribe".
                  </p>
                  <div className="setting-row">
                    <span>List storage</span>
                    <strong>Local app only</strong>
                  </div>
                  <div className="setting-row">
                    <span>Enforcement</span>
                    <strong>Before every send</strong>
                  </div>
                  <div className="setting-row">
                    <span>Demo status</span>
                    <strong>Not editable here</strong>
                  </div>
                </section>

                <section className="card">
                  <h2 className="section-title">Storage and safety</h2>
                  <p className="body-text">
                    The app never sends email from Vercel, submits forms, or contacts publishers. Research is only run
                    when you click an action. The OpenAI API key stays on the server and is never sent to the browser.
                  </p>
                  <div className="setting-row">
                    <span>Local app storage</span>
                    <strong>SQLite + backups</strong>
                  </div>
                  <div className="setting-row">
                    <span>Vercel storage</span>
                    <strong>Browser session only</strong>
                  </div>
                  <div className="setting-row">
                    <span>Email credentials</span>
                    <strong>Local, gitignored storage only</strong>
                  </div>
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
