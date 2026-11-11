"use client";

import { useEffect, useRef, useState } from "react";
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

function safeHref(value: any): string {
  const raw = String(value || "").trim();
  if (!raw || raw.length > 2048) return "";
  try {
    const u = new URL(raw);
    if (u.protocol !== "https:") return "";
    if (u.username || u.password) return "";
    const host = u.hostname.toLowerCase().replace(/\.$/, "");
    if (!host.includes(".") || host === "localhost" || host.endsWith(".local") || host.endsWith(".internal")) return "";
    if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) return "";
    if (!/^[a-z0-9.-]+$/.test(host)) return "";
    if (host.split(".").some((label) => label.startsWith("xn--"))) return "";
    if (!/^[a-z]{2,}$/.test(host.split(".").pop() || "")) return "";
    return raw;
  } catch {
    return "";
  }
}

function SafeA({
  url,
  children,
  ...rest
}: { url: any; children: ReactNode } & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  const href = safeHref(url);
  if (!href) {
    return <span className="meta">Link withheld: not a verified website URL</span>;
  }
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" title="Unverified source link" {...rest}>
      {children}
    </a>
  );
}

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
const stepsOfDigitalPhase: Record<DigitalPhase, DigitalStep[]> = {
  Research: ["Article", "PR angles"],
  Prospects: ["Opportunities", "Journalists"],
  Outreach: ["Outreach"],
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

  // Domain scan state
  const [domainInput, setDomainInput] = useState("");
  const [topicHint, setTopicHint] = useState("");
  const [loadingScan, setLoadingScan] = useState(false);
  const [scanResult, setScanResult] = useState<AnyObj | null>(null);
  const [errScan, setErrScan] = useState<string | null>(null);

  // Already-used articles (persisted in this browser so pitched targets are not repeated)
  const USED_URLS_KEY = "pr_used_urls_v1";
  const [usedUrls, setUsedUrls] = useState<string[]>(() => {
    try {
      const raw = typeof window !== "undefined" ? window.localStorage.getItem(USED_URLS_KEY) : null;
      const parsed = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(parsed)) return [];
      const normed = parsed
        .filter((u) => typeof u === "string")
        .map((u) => {
          try {
            const url = new URL(u);
            const host = url.hostname.toLowerCase().replace(/^www\./, "");
            return `https://${host}${url.pathname.replace(/\/+$/, "")}${url.search}`.toLowerCase();
          } catch {
            return String(u).replace(/\/+$/, "").toLowerCase();
          }
        })
        .filter(Boolean);
      return Array.from(new Set(normed));
    } catch {
      return [];
    }
  });
  const [hideUsed, setHideUsed] = useState(false);

  useEffect(() => {
    try {
      window.localStorage.setItem(USED_URLS_KEY, JSON.stringify(usedUrls));
    } catch {
      // Private-mode storage may be unavailable; the in-memory list still works.
    }
  }, [usedUrls]);

  function normalizeUrl(url: any): string {
    const raw = String(url || "").trim();
    if (!raw) return "";
    try {
      const u = new URL(raw);
      const host = u.hostname.toLowerCase().replace(/^www\./, "");
      let path = u.pathname.replace(/\/+$/, "");
      return `https://${host}${path}${u.search}`.toLowerCase();
    } catch {
      return raw.replace(/\/+$/, "").toLowerCase();
    }
  }

  function isUsed(url: any): boolean {
    const norm = normalizeUrl(url);
    return !!norm && usedUrls.includes(norm);
  }

  function toggleUsed(url: any) {
    const norm = normalizeUrl(url);
    if (!norm) return;
    setUsedUrls((current) =>
      current.includes(norm) ? current.filter((u) => u !== norm) : [...current, norm]
    );
  }

  function UsedBadge() {
    return <span className="status-pill active">Used</span>;
  }

  function csvCell(cell: any): string {
    let text = String(cell ?? "");
    // Spreadsheet formula injection: a leading = + - @ (or tab tricks)
    // would turn AI-provided text into a live formula on import.
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return `"${text.replace(/"/g, '""')}"`;
  }

  function sortByScore<T extends AnyObj>(items: T[]): T[] {
    const arr = [...items];
    if (!arr.some((x) => Number((x as AnyObj).pr_score) > 0)) return arr;
    return arr.sort(
      (a, b) => (Number((b as AnyObj).pr_score) || 0) - (Number((a as AnyObj).pr_score) || 0)
    );
  }

  function ScoreLine({ item }: { item: AnyObj }) {
    if (!(Number(item.pr_score) > 0)) return null;
    const reasons = Array.isArray(item.pr_score_reasons) ? item.pr_score_reasons : [];
    return (
      <p className="meta">
        <strong>Score: {item.pr_score}/100</strong>
        {reasons.length > 0 && ` — ${reasons.join("; ")}`}
      </p>
    );
  }

  function UsedToggle({ url }: { url: any }) {
    const used = isUsed(url);
    return (
      <button
        type="button"
        className={used ? "btn-primary" : "btn-secondary"}
        onClick={() => toggleUsed(url)}
        title={used ? "Remove the Used mark" : "Mark as already used so it is skipped next time"}
      >
        {used ? "✓ Used" : "Mark used"}
      </button>
    );
  }

  // PR workflow state
  const [selectedAngle, setSelectedAngle] = useState<AnyObj | null>(null);
  const [loadingOpp, setLoadingOpp] = useState(false);
  const [opportunities, setOpportunities] = useState<AnyObj | null>(null);
  const [oppByAngle, setOppByAngle] = useState<Record<string, AnyObj>>({});
  const [errOpp, setErrOpp] = useState<string | null>(null);

  const [selectedOpp, setSelectedOpp] = useState<AnyObj | null>(null);
  const [loadingJourn, setLoadingJourn] = useState(false);
  const [journalists, setJournalists] = useState<AnyObj | null>(null);
  const [writersByOpp, setWritersByOpp] = useState<Record<string, AnyObj>>({});
  const [errJourn, setErrJourn] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, AnyObj>>({});

  // Listicle inclusion drafts
  const [listicleDrafts, setListicleDrafts] = useState<Record<string, AnyObj>>({});
  const [loadingListDraft, setLoadingListDraft] = useState<string | null>(null);
  const [errListDraft, setErrListDraft] = useState<string | null>(null);
  const [contactByItem, setContactByItem] = useState<Record<string, AnyObj>>({});
  const [policyByItem, setPolicyByItem] = useState<Record<string, AnyObj>>({});

  const [loadingDraft, setLoadingDraft] = useState<string | null>(null);
  const [errDraft, setErrDraft] = useState<string | null>(null);
  const [checkedPeople, setCheckedPeople] = useState<string[]>([]);
  const [emailByPerson, setEmailByPerson] = useState<Record<string, AnyObj>>({});
  const [loadingEmail, setLoadingEmail] = useState<string | null>(null);

  // Media library: every researched writer auto-saved, persisted in this browser.
  const MEDIA_LIBRARY_KEY = "pr_media_library_v1";
  const [mediaLibrary, setMediaLibrary] = useState<Record<string, AnyObj>>(() => {
    try {
      const raw = typeof window !== "undefined" ? window.localStorage.getItem(MEDIA_LIBRARY_KEY) : null;
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  });
  const [libSearch, setLibSearch] = useState("");
  const [libEmailOnly, setLibEmailOnly] = useState(false);
  const [collectQuery, setCollectQuery] = useState("");
  const [loadingCollect, setLoadingCollect] = useState(false);
  const [errCollect, setErrCollect] = useState<string | null>(null);
  const [collectMsg, setCollectMsg] = useState<string | null>(null);
  const OUTCOME_KEY = "pr_pitch_outcomes_v1";
  const [pitchOutcomes, setPitchOutcomes] = useState<Record<string, AnyObj>>(() => {
    try {
      const raw = typeof window !== "undefined" ? window.localStorage.getItem(OUTCOME_KEY) : null;
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(OUTCOME_KEY, JSON.stringify(pitchOutcomes));
    } catch {
      // Private-mode storage may be unavailable; the in-memory list still works.
    }
  }, [pitchOutcomes]);

  // Campaigns: named workspace snapshots with live outcome counts.
  const CAMPAIGNS_KEY = "pr_campaigns_v1";
  const [campaigns, setCampaigns] = useState<Record<string, AnyObj>>(() => {
    try {
      const raw = typeof window !== "undefined" ? window.localStorage.getItem(CAMPAIGNS_KEY) : null;
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(CAMPAIGNS_KEY, JSON.stringify(campaigns));
    } catch {
      // Private-mode storage may be unavailable; the in-memory list still works.
    }
  }, [campaigns]);

  function saveCampaign() {
    if (!analysis && Object.keys(drafts).length === 0 && !listicles) return;
    const name = window.prompt(
      "Campaign name",
      analysis?.article_title || (listicles ? `Listicles: ${listicles.search_theme}` : "") || "Untitled campaign"
    );
    if (!name || !name.trim()) return;
    const id = `c${Date.now()}`;
    const today = new Date().toISOString().slice(0, 10);
    setCampaigns((current) => ({
      ...current,
      [id]: {
        id,
        name: name.trim(),
        created: today,
        workflow,
        urlInputs,
        analyses,
        analysis,
        activeUrl,
        selectedAngle,
        oppByAngle,
        selectedOpp,
        writersByOpp,
        drafts,
        draftKeys: Object.keys(drafts),
        usedUrls,
        listicleDrafts,
        listicleDraftKeys: Object.keys(listicleDrafts),
        listForm,
        listicles,
        selectedItem,
        contact,
        policy,
        contactByItem,
        policyByItem,
        emailByPerson,
        domainInput,
        topicHint,
        scanResult,
      },
    }));
  }

  function loadCampaign(id: string) {
    const c = campaigns[id];
    if (!c) return;
    setUrlInputs(Array.isArray(c.urlInputs) && c.urlInputs.length ? c.urlInputs : [""]);
    setAnalyses(Array.isArray(c.analyses) ? c.analyses : []);
    setAnalysis(c.analysis || null);
    setActiveUrl(c.activeUrl || "");
    setSelectedAngle(c.selectedAngle || null);
    setOppByAngle(c.oppByAngle || {});
    setOpportunities(
      c.selectedAngle && c.oppByAngle ? (c.oppByAngle[angleKey(c.selectedAngle)] ?? null) : null
    );
    setSelectedOpp(c.selectedOpp || null);
    setWritersByOpp(c.writersByOpp || {});
    setJournalists(
      c.selectedOpp && c.writersByOpp ? (c.writersByOpp[oppKey(c.selectedOpp)] ?? null) : null
    );
    setDrafts(c.drafts || {});
    setListicleDrafts(c.listicleDrafts || {});
    setListForm(c.listForm || {
      search_theme: "",
      related_queries: "",
      target_audience: "All relevant audiences",
      target_market: "Global English-language",
      competitors: "",
      max_results: 8,
    });
    setListicles(c.listicles || null);
    setSelectedItem(c.selectedItem || null);
    setContact(c.contact || null);
    setPolicy(c.policy || null);
    setContactByItem(c.contactByItem || {});
    setPolicyByItem(c.policyByItem || {});
    setEmailByPerson(c.emailByPerson && typeof c.emailByPerson === "object" ? c.emailByPerson : {});
    setDomainInput(typeof c.domainInput === "string" ? c.domainInput : "");
    setTopicHint(typeof c.topicHint === "string" ? c.topicHint : "");
    setScanResult(c.scanResult || null);
    if (Array.isArray(c.usedUrls) && c.usedUrls.length > 0) {
      setUsedUrls((current) => {
        const merged = [...current];
        for (const u of c.usedUrls) {
          const norm = normalizeUrl(u);
          if (norm && !merged.includes(norm)) merged.push(norm);
        }
        return merged;
      });
    }
    if (c.listicleDrafts && typeof c.listicleDrafts === "object") {
      setListicleDrafts(c.listicleDrafts);
    }
    setCheckedPeople([]);
    setErrOpp(null);
    setErrJourn(null);
    setErrDraft(null);
    setErrList(null);
    setErrContact(null);
    setErrPolicy(null);
    setErrListDraft(null);
    setShowStart(false);
    setWorkflow(c.workflow === "listicles" ? "listicles" : "digital");
    setNav("Workspace");
    if (c.workflow === "listicles") {
      setListicleStep(
        c.listicleDrafts && Object.keys(c.listicleDrafts).length
          ? "Outreach"
          : c.listicles
            ? "Prospects"
            : "Search"
      );
      return;
    }
    setDigitalStep(
      c.drafts && Object.keys(c.drafts).length
        ? "Outreach"
        : c.selectedOpp
          ? "Journalists"
          : c.selectedAngle
            ? "Opportunities"
            : "Article"
    );
  }

  function setOutcome(draftId: string, patch: AnyObj) {
    setPitchOutcomes((current) => ({
      ...current,
      [draftId]: {
        status: "Draft",
        ...(current[draftId] || {}),
        ...patch,
        updated: new Date().toISOString().slice(0, 10),
      },
    }));
  }

  function draftStatusFor(recipientName: any): string {
    const entry = Object.values(drafts).find(
      (d: AnyObj) => String(d.recipient_name || "").toLowerCase() === String(recipientName || "").toLowerCase()
    );
    if (!entry) return "";
    const id = Object.keys(drafts).find((k) => drafts[k] === entry) || "";
    return pitchOutcomes[id]?.status || "Draft";
  }

  const outcomeCounts = Object.keys(drafts).reduce(
    (acc: Record<string, number>, id) => {
      const s = pitchOutcomes[id]?.status || "Draft";
      acc[s] = (acc[s] || 0) + 1;
      return acc;
    },
    {}
  );

  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncErr, setSyncErr] = useState<string | null>(null);
  const [selectedDrafts, setSelectedDrafts] = useState<string[]>([]);

  // Remaining research budget for this person today (read-only check).
  const [quota, setQuota] = useState<AnyObj | null>(null);
  const [drReady, setDrReady] = useState(false);
  async function refreshQuota() {
    try {
      const res = await fetch("/api/analyze", { cache: "no-store" });
      const data = await res.json().catch(() => ({}));
      if (res.ok && typeof data?.remaining === "number") setQuota(data);
      if (res.ok && typeof data?.dr_ready === "boolean") setDrReady(data.dr_ready);
    } catch {
      // Budget display is optional; never block the UI on it.
    }
  }
  useEffect(() => {
    void refreshQuota();
    // Keep "Calls left today" fresh while working; the check costs no budget.
    const t = setInterval(() => {
      void refreshQuota();
    }, 60000);
    return () => clearInterval(t);
  }, []);

  // Ahrefs Domain Rating cache: domain -> DR number (null = lookup failed).
  const [drByDomain, setDrByDomain] = useState<Record<string, number | null>>({});
  const [loadingDr, setLoadingDr] = useState(false);
  const [drOnly, setDrOnly] = useState(false);
  const DR_CUTOFF = 50;

  function domainOf(url: any): string {
    try {
      return new URL(String(url || "")).hostname.replace(/^www\./, "").toLowerCase();
    } catch {
      return "";
    }
  }

  async function checkDr(urls: any[]) {
    const domains = Array.from(
      new Set(urls.map(domainOf).filter((d) => d && !(d in drByDomain)))
    ).slice(0, 10);
    if (domains.length === 0) return;
    setLoadingDr(true);
    setRetryMsg(null);
    try {
      const data = await callApi("site-metrics", { domains }, (a) =>
        setRetryMsg(`Checking Domain Rating - retry ${a}/3...`)
      );
      setDrByDomain((current) => {
        const next = { ...current };
        for (const m of data?.metrics ?? []) {
          if (m?.domain) next[m.domain] = typeof m.dr === "number" ? m.dr : null;
        }
        return next;
      });
      await refreshQuota();
    } catch (err: any) {
      setRetryMsg(null);
      window.alert(err?.message || "DR check failed. Add AHREFS_API_KEY in Vercel first.");
    } finally {
      setLoadingDr(false);
      setRetryMsg(null);
    }
  }

  function DrBadge({ url }: { url: any }) {
    const d = domainOf(url);
    if (!d || !(d in drByDomain)) return null;
    const dr = drByDomain[d];
    if (dr === null || dr === undefined) return <span className="status-pill">DR ?</span>;
    return (
      <span className={`status-pill ${dr >= DR_CUTOFF ? "active" : ""}`} title="Domain Rating by Ahrefs">
        DR {dr}
      </span>
    );
  }

  // Prospect-list filtering that never silently empties the list: domains with
  // no DR rating yet always pass the DR filter, and the caller is told how
  // many are hidden so it can prompt for a Check DR run.
  function filterProspects<T extends AnyObj>(items: T[], getUrl: (x: T) => any) {
    const visible: T[] = [];
    let hiddenUsed = 0;
    let hiddenDr = 0;
    let drKnown = false;
    for (const item of items) {
      const url = getUrl(item);
      if (hideUsed && isUsed(url)) {
        hiddenUsed += 1;
        continue;
      }
      const d = domainOf(url);
      const dr = d ? drByDomain[d] : undefined;
      if (dr !== undefined && dr !== null) drKnown = true;
      if (drOnly && dr !== undefined && dr !== null && dr < DR_CUTOFF) {
        hiddenDr += 1;
        continue;
      }
      visible.push(item);
    }
    return { visible, hiddenUsed, hiddenDr, drKnown };
  }

  function FilterNotes({ hiddenUsed, hiddenDr, drKnown }: { hiddenUsed: number; hiddenDr: number; drKnown: boolean }) {
    return (
      <>
        {hiddenUsed > 0 && (
          <p className="meta">
            {hiddenUsed} hidden by Hide used. Untick it to see everything.
          </p>
        )}
        {hiddenDr > 0 && (
          <p className="meta">
            {hiddenDr} hidden by the DR {DR_CUTOFF}+ filter.
          </p>
        )}
        {drOnly && !drKnown && (
          <p className="meta">
            No ratings yet — press <strong>Check DR</strong> first, otherwise the filter cannot judge anything.
          </p>
        )}
      </>
    );
  }

  function budgetAllows(count: number): boolean {
    if (!quota || typeof quota.remaining !== "number") return true;
    if (quota.remaining >= count) return true;
    return window.confirm(
      `This would use ${count} research calls but only ${quota.remaining} are left today. Continue anyway?`
    );
  }

  // Multi-call actions state their cost before spending anything.
  function confirmBulk(label: string, count: number): boolean {
    if (count <= 1) return true;
    const left =
      quota && typeof quota.remaining === "number" ? `, ${quota.remaining} left today` : "";
    return window.confirm(`${label} will use ${count} research calls${left}. Continue?`);
  }  // Auto-sync to the sheet after pitch writing / status changes.
  const AUTO_SYNC_KEY = "pr_autosync_v1";
  const [autoSync, setAutoSync] = useState<boolean>(() => {
    try {
      const raw = typeof window !== "undefined" ? window.localStorage.getItem(AUTO_SYNC_KEY) : null;
      return raw === null ? true : raw === "1";
    } catch {
      return true;
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(AUTO_SYNC_KEY, autoSync ? "1" : "0");
    } catch {
      // ignore
    }
  }, [autoSync]);

  const syncTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sheet connection status
  const [sheetStatus, setSheetStatus] = useState<AnyObj | null>(null);
  const [checkingSheet, setCheckingSheet] = useState(false);
  async function testSheetConnection() {
    setCheckingSheet(true);
    try {
      const res = await fetch("/api/sheet", { cache: "no-store" });
      const data = await res.json().catch(() => ({}));
      setSheetStatus(data);
    } catch (err: any) {
      setSheetStatus({ configured: false, error: err?.message || "Unreachable" });
    } finally {
      setCheckingSheet(false);
    }
  }
  useEffect(() => {
    void testSheetConnection();
  }, []);

  async function copySetupScript() {
    try {
      const res = await fetch("/apps-script/pitch-sheet.js", { cache: "no-store" });
      const text = await res.text();
      await navigator.clipboard.writeText(text);
      setSyncMsg("Setup script copied. Paste it into Apps Script, add your token, deploy.");
    } catch {
      setSyncErr("Could not copy the script. Open /apps-script/pitch-sheet.js instead.");
    }
  }

  function toggleDraftSel(id: string) {
    setSelectedDrafts((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    );
  }

  function bulkStatus(status: string) {
    if (selectedDrafts.length === 0) return;
    const today = new Date().toISOString().slice(0, 10);
    setPitchOutcomes((current) => {
      const next = { ...current };
      for (const id of selectedDrafts) {
        next[id] = { ...(current[id] || {}), status, updated: today };
      }
      return next;
    });
    setSelectedDrafts([]);
  }

  function toggleAllDrafts(ids: string[]) {
    setSelectedDrafts((current) => (current.length === ids.length ? [] : ids));
  }

  async function postSheetTab(tab: string, rows: string[][]) {
    const res = await fetch("/api/sheet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tab, rows }),
      cache: "no-store",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || `Sheet sync failed (${tab}).`);
    return data;
  }

  function splitDraftId(id: string): string {
    const sep = id.lastIndexOf("##");
    return sep >= 0 ? id.slice(0, sep) : "";
  }

  function buildPitchRows(): string[][] {
    const today = new Date().toISOString().slice(0, 10);
    const rows: string[][] = [];
    for (const id of Object.keys(drafts)) {      const d = drafts[id];
      const oppUrl = splitDraftId(id);
      let angleName = "";
      let opp: AnyObj | null = null;
      for (const [ak, res] of Object.entries(oppByAngle)) {
        const found = (res?.opportunities ?? []).find(
          (o: AnyObj) => o.article_url === oppUrl
        );
        if (found) {
          angleName = ak;
          opp = found;
          break;
        }
      }
      const out = pitchOutcomes[id] || {};
      const emailRec = emailByPerson[id];
      const email = emailRec && !emailRec.__error ? emailRec.email || "" : "";
      let domain = "";
      try {
        domain = new URL(oppUrl).hostname.replace(/^www\./, "");
      } catch {
        domain = "";
      }
      rows.push([
        id,
        today,
        angleName,
        d.publication || "",
        domain,
        opp?.article_title || d.target_title || "",
        oppUrl,
        isUsed(oppUrl) ? "yes" : "no",
        String(opp?.pr_fit || ""),
        String(opp?.pr_score || ""),
        d.recipient_name || "",
        d.recipient_role || "",
        email,
        d.subject_line || "",
        d.message_body || "",
        out.status || "Draft",
        out.coverage_url || "",
      ]);
    }
    return rows;
  }

  function buildCoverageRows(): string[][] {
    const rows: string[][] = [];
    for (const id of Object.keys(drafts)) {
      const out = pitchOutcomes[id] || {};
      if (out.status !== "Covered") continue;
      const d = drafts[id];
      const oppUrl = splitDraftId(id);
      let opp: AnyObj | null = null;
      for (const res of Object.values(oppByAngle)) {
        const found = (res?.opportunities ?? []).find(
          (o: AnyObj) => o.article_url === oppUrl
        );
        if (found) {
          opp = found;
          break;
        }
      }
      rows.push([
        id,
        out.updated || new Date().toISOString().slice(0, 10),
        d.recipient_name || "",
        d.publication || "",
        opp?.article_title || d.target_title || "",
        oppUrl,
        d.subject_line || "",
        out.coverage_url || "",
        "Covered",
      ]);
    }
    return rows;
  }

  function buildContactRows(): string[][] {
    return (Object.entries(mediaLibrary) as Array<[string, AnyObj]>).map(([key, e]) => [
      key,
      e.name || "",
      e.publication || "",
      e.role || "",
      e.beat || "",
      e.email || "",
      e.contact_page || "",
      e.profile_url || "",
      e.article_title || "",
      e.article_url || "",
      (e.angles ?? []).slice(-1)[0] || "",
      e.last_seen || "",
      draftStatusFor(e.name) || "",
    ]);
  }

  function buildListicleRows(): string[][] {
    const today = new Date().toISOString().slice(0, 10);
    const rows: string[][] = [];
    for (const id of Object.keys(listicleDrafts)) {
      const d = listicleDrafts[id];
      const item = d.__item || {};
      const out = pitchOutcomes[id] || {};
      rows.push([
        id,
        today,
        item.publication || d.publication || "",
        item.listicle_title || d.target_title || "",
        item.listicle_url || "",
        item.placement_type || "",
        d.recipient_name || "",
        d.recipient_role || "",
        "",
        d.subject_line || "",
        d.message_body || "",
        out.status || "Draft",
        out.coverage_url || "",
      ]);
    }
    return rows;
  }

  async function syncToSheet(silent = false) {
    const digitalRows = buildPitchRows();
    const listRows = buildListicleRows();
    if (digitalRows.length === 0 && listRows.length === 0) return;
    if (!silent) {
      setSyncing(true);
      setSyncMsg(null);
      setSyncErr(null);
    }
    try {
      let pitches = { updated: 0, appended: 0 };
      let listicles = { updated: 0, appended: 0 };
      if (digitalRows.length > 0) {
        pitches = await postSheetTab("Pitches", digitalRows);
      }
      if (listRows.length > 0) {
        listicles = await postSheetTab("Listicles", listRows);
      }
      const coverageRows = [...buildCoverageRows(), ...buildListicleCoverageRows()];
      let coverage = { updated: 0, appended: 0 };
      if (coverageRows.length > 0) {
        coverage = await postSheetTab("Coverage", coverageRows);
      }
      setSyncErr(null);
      setSyncMsg(
        `Sheet updated — Pitches: ${pitches.appended} added, ${pitches.updated} refreshed; ` +
          `Listicles: ${listicles.appended} added, ${listicles.updated} refreshed; ` +
          `Coverage: ${coverage.appended} added, ${coverage.updated} refreshed.`
      );
    } catch (err: any) {
      setSyncErr(err?.message || "Sheet sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  // Auto-sync: state-driven so it always sees the latest drafts.
  useEffect(() => {
    if (!autoSync) return;
    if (Object.keys(drafts).length === 0 && Object.keys(listicleDrafts).length === 0) return;
    const t = setTimeout(() => {
      void syncToSheet(true);
    }, 2000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drafts, listicleDrafts, pitchOutcomes, autoSync]);

  function buildListicleCoverageRows(): string[][] {
    const rows: string[][] = [];
    for (const id of Object.keys(listicleDrafts)) {
      const out = pitchOutcomes[id] || {};
      if (out.status !== "Covered") continue;
      const d = listicleDrafts[id];
      const item = d.__item || {};
      rows.push([
        id,
        out.updated || new Date().toISOString().slice(0, 10),
        d.recipient_name || "",
        item.publication || d.publication || "",
        item.listicle_title || d.target_title || "",
        item.listicle_url || "",
        d.subject_line || "",
        out.coverage_url || "",
        "Covered",
      ]);
    }
    return rows;
  }

  async function syncContactsToSheet() {
    if (Object.keys(mediaLibrary).length === 0) return;
    setSyncing(true);
    setSyncMsg(null);
    setSyncErr(null);
    try {
      const data = await postSheetTab("Contacts", buildContactRows());
      setCollectMsg(`Contacts synced: ${data.appended} added, ${data.updated} refreshed.`);
    } catch (err: any) {
      setErrCollect(err?.message || "Sheet sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  async function collectWriters(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const query = collectQuery.trim();
    if (!query) {
      setErrCollect("Describe what to collect, e.g. fintech reporters at TechCrunch.");
      return;
    }
    setLoadingCollect(true);
    setErrCollect(null);
    setCollectMsg(null);
    setRetryMsg(null);
    try {
      const data = await callApi("collect-writers", { query }, (a) =>
        setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      const people = data?.journalists ?? [];
      saveToLibrary(people, null, null);
      setCollectMsg(
        people.length > 0
          ? `Saved ${people.length} contact(s) to the library. ${data?.research_summary || ""}`
          : "No verifiable writers found. Try a more specific beat or outlet."
      );
    } catch (err: any) {
      setErrCollect(err?.message || "Something went wrong");
    } finally {
      setLoadingCollect(false);
      setRetryMsg(null);
    }
  }

  useEffect(() => {
    try {
      window.localStorage.setItem(MEDIA_LIBRARY_KEY, JSON.stringify(mediaLibrary));
    } catch {
      // Private-mode storage may be unavailable; the in-memory list still works.
    }
  }, [mediaLibrary]);

  function libraryKey(name: any, publication: any): string {
    return `${String(name || "").trim().toLowerCase()} @ ${String(publication || "").trim().toLowerCase()}`;
  }

  function saveToLibrary(people: AnyObj[], opportunity?: AnyObj | null, angle?: AnyObj | null) {
    if (!Array.isArray(people) || people.length === 0) return;
    const today = new Date().toISOString().slice(0, 10);
    const angleText = String(angle?.angle || "").trim();
    setMediaLibrary((current) => {
      const next = { ...current };
      for (const p of people) {
        const key = libraryKey(p.name, p.publication);
        if (key === " @ ") continue;
        const prev = next[key] || {};
        const angles = Array.isArray(prev.angles) ? [...prev.angles] : [];
        if (angleText && !angles.includes(angleText)) angles.push(angleText);
        next[key] = {
          name: p.name || prev.name || "",
          publication: p.publication || prev.publication || "",
          role: p.current_role || prev.role || "",
          beat: p.topic_covered || prev.beat || "",
          article_title: p.relevant_article_title || prev.article_title || "",
          article_url: p.relevant_article_url || prev.article_url || "",
          profile_url:
            p.author_profile_or_contact_page && p.author_profile_or_contact_page !== "Unknown"
              ? p.author_profile_or_contact_page
              : prev.profile_url || "",
          why: p.why_relevant || prev.why || "",
          pitch_angle: p.suggested_pitch_angle || prev.pitch_angle || "",
          opportunity_title: opportunity?.article_title || prev.opportunity_title || "",
          opportunity_url: opportunity?.article_url || prev.opportunity_url || "",
          angles: angles.slice(-5),
          email: prev.email || "",
          email_evidence: prev.email_evidence || "",
          contact_page: prev.contact_page || "",
          first_seen: prev.first_seen || today,
          last_seen: today,
        };
      }
      return next;
    });
  }

  function mergeLibraryEmail(person: AnyObj, contact: AnyObj) {
    const key = libraryKey(person.name, person.publication);
    if (key === " @ ") return;
    const today = new Date().toISOString().slice(0, 10);
    setMediaLibrary((current) => {
      const prev = current[key] || {
        name: person.name || "",
        publication: person.publication || "",
        first_seen: today,
        angles: [],
      };
      return {
        ...current,
        [key]: {
          ...prev,
          email: contact.email && contact.email !== "Not publicly found" ? contact.email : prev.email || "",
          email_evidence: contact.evidence || prev.email_evidence || "",
          contact_page:
            contact.contact_page_url && contact.contact_page_url !== "Unknown"
              ? contact.contact_page_url
              : prev.contact_page || "",
          last_seen: today,
        },
      };
    });
  }

  function downloadLibraryCsv(entries: AnyObj[]) {
    const header = [
      "name", "publication", "role", "beat", "email", "contact_page",
      "profile_url", "source_article", "source_url", "last_angle", "last_seen",
    ];
    const rows = entries.map((e) => [
      e.name || "", e.publication || "", e.role || "", e.beat || "",
      e.email || "", e.contact_page || "", e.profile_url || "",
      e.article_title || "", e.article_url || "",
      (e.angles ?? []).slice(-1)[0] || "", e.last_seen || "",
    ]);
    const csv = [header, ...rows]
      .map((row) => row.map(csvCell).join(","))
      .join("\r\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "media_library.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  function personKey(name: any): string {
    return draftKey(oppKey(selectedOpp), name);
  }

  function togglePerson(name: any) {
    const key = String(name || "");
    setCheckedPeople((current) =>
      current.includes(key) ? current.filter((n) => n !== key) : [...current, key]
    );
  }

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
  function listDraftKey(url: any, name: any): string {
    return `list::${String(url || "")}##${String(name || "contact")}`;
  }

  async function writeAllListicleDrafts() {
    const entries: Array<{ item: AnyObj; person: AnyObj }> = [];
    for (const item of listicles?.opportunities ?? []) {
      const c = contactByItem[item.listicle_url];
      for (const person of c?.contacts ?? []) {
        entries.push({ item, person });
      }
    }
    if (entries.length === 0) {
      setErrListDraft("Run Find contact on at least one listicle first.");
      return;
    }
    if (!budgetAllows(entries.length)) return;
    if (!confirmBulk("Write all inclusion requests", entries.length)) return;
    setLoadingListDraft("__all__");
    setErrListDraft(null);
    setRetryMsg(null);
    const failures: string[] = [];
    let done = 0;
    try {
      for (let index = 0; index < entries.length; index += 1) {
        const { item, person } = entries[index];
        setRetryMsg(`Writing inclusion requests ${index + 1} of ${entries.length}...`);
        try {
          const data = await callApi(
            "listicle-draft",
            { item, contact: person },
            (a) => setRetryMsg(`Writing requests ${index + 1} of ${entries.length} - retry ${a}/3...`)
          );
          setListicleDrafts((current) => ({
            ...current,
            [listDraftKey(item.listicle_url, person.contact_name)]: { ...data, __item: item },
          }));
          markUrlsUsed([item.listicle_url]);
          done += 1;
        } catch (err: any) {
          failures.push(`${shortText(person.contact_name, 30)}: ${err?.message || "failed"}`);
          if (String(err?.message || "").match(/429|limit|budget|Too many/i)) break;
        }
      }
      if (failures.length > 0) {
        setErrListDraft(`Wrote ${done} of ${entries.length}. Failures: ${failures.join(" | ")}`);
      }
      if (done > 0) setListicleStep("Outreach");
      void refreshQuota();
    } finally {
      setLoadingListDraft(null);
      setRetryMsg(null);
    }
  }

  async function writeListicleDraft(item: AnyObj, person: AnyObj) {
    const key = listDraftKey(item.listicle_url, person.contact_name);
    setLoadingListDraft(key);
    setErrListDraft(null);
    setRetryMsg(null);
    try {
      const data = await callApi(
        "listicle-draft",
        { item, contact: person },
        (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setListicleDrafts((current) => ({ ...current, [key]: { ...data, __item: item } }));
      markUrlsUsed([item.listicle_url]);
      setListicleStep("Outreach");
    } catch (err: any) {
      setErrListDraft(err?.message || "Draft generation failed");
    } finally {
      setLoadingListDraft(null);
      setRetryMsg(null);
    }
  }

  const angleCount = analysis?.pr_angles?.length || 0;
  const oppEntries = Object.entries(oppByAngle);
  const oppCount =
    oppEntries.length > 0
      ? oppEntries.reduce((n, [, res]) => n + (res?.opportunities?.length || 0), 0)
      : opportunities?.opportunities?.length || 0;
  const writerEntries = Object.entries(writersByOpp);
  const journCount =
    writerEntries.length > 0
      ? writerEntries.reduce((n, [, res]) => n + (res?.journalists?.length || 0), 0)
      : journalists?.journalists?.length || 0;
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
    setDrafts({});
    setScanResult(null);
    setDomainInput("");
    setTopicHint("");
    setErrScan(null);
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
    setSelectedItem(null);
    setContact(null);
    setPolicy(null);
    setContactByItem({});
    setPolicyByItem({});
    setListicleDrafts({});
    setErrList(null);
    setErrContact(null);
    setErrPolicy(null);
    setErrListDraft(null);
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
    // NOTE: drafts and listicle drafts are intentionally kept: they are keyed
    // by article URL, so regenerating an analysis no longer destroys pitches.
    // Only "Start new" clears them (see startNewDigital).
    setSelectedAngle(null);
    setOpportunities(null);
    setOppByAngle({});
    setSelectedOpp(null);
    setJournalists(null);
    setWritersByOpp({});
    setCheckedPeople([]);
    setEmailByPerson({});
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
    await analyzeUrls(urls, true);
  }

  // Domain-scan multi-select for bulk analysis.
  const [selectedScan, setSelectedScan] = useState<string[]>([]);
  // Which single URL is currently being analyzed (per-card spinner).
  const [analyzingUrl, setAnalyzingUrl] = useState<string | null>(null);

  function toggleScan(url: any) {
    const key = String(url || "");
    setSelectedScan((current) =>
      current.includes(key) ? current.filter((u) => u !== key) : [...current, key]
    );
  }

  async function analyzeUrls(urls: string[], advance = false) {
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
        if (advance) setDigitalStep("PR angles");
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

  async function scanDomain(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const domain = domainInput.trim();
    if (!domain) {
      setErrScan("Enter a domain, e.g. example.com.");
      return;
    }
    setLoadingScan(true);
    setErrScan(null);
    setScanResult(null);
    setRetryMsg(null);
    try {
      const data = await callApi(
        "domain-scan",
        { domain, topic_hint: topicHint.trim() },
        (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setScanResult(data);
    } catch (err: any) {
      setErrScan(err?.message || "Something went wrong");
    } finally {
      setLoadingScan(false);
      setRetryMsg(null);
    }
  }

  async function useScannedArticle(articleUrl: string) {
    if (!articleUrl?.startsWith("https://")) {
      setErrAnalyze("That article URL is not usable. Pick another.");
      return;
    }
    setUrlInputs([articleUrl]);
    setAnalyzingUrl(articleUrl);
    try {
      await analyzeUrls([articleUrl], true);
    } finally {
      setAnalyzingUrl(null);
    }
  }

  async function analyzeSelectedScan() {
    const urls = selectedScan.filter((u) => u.startsWith("https://")).slice(0, 5);
    if (urls.length === 0) return;
    setUrlInputs(urls);
    setAnalyzingUrl("__bulk__");
    try {
      await analyzeUrls(urls, true);
      setSelectedScan([]);
    } finally {
      setAnalyzingUrl(null);
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

  function angleKey(angle: AnyObj | null): string {
    return String(angle?.angle || "").trim();
  }

  function oppKey(o: AnyObj | null): string {
    return String(o?.article_url || "").trim();
  }

  function draftKey(oppUrl: string, name: any): string {
    return `${oppUrl}##${String(name || "contact")}`;
  }

  function selectAngleCached(angle: AnyObj) {
    setSelectedAngle(angle);
    setOpportunities(oppByAngle[angleKey(angle)] ?? null);
    // Drop the previous angle's selection so the Journalists step never shows
    // writers researched for a different angle.
    setSelectedOpp(null);
    setJournalists(null);
    setCheckedPeople([]);
    setEmailByPerson({});
    setErrOpp(null);
    setErrJourn(null);
  }

  function pickAngle(angle: AnyObj) {
    if (oppByAngle[angleKey(angle)]) {
      selectAngleCached(angle);
      setDigitalStep("Opportunities");
    } else {
      researchAngle(angle);
    }
  }

  function selectOppCached(opportunity: AnyObj) {
    setSelectedOpp(opportunity);
    setJournalists(writersByOpp[oppKey(opportunity)] ?? null);
    setCheckedPeople([]);
    setErrJourn(null);
  }

  async function findEmailFor(person: AnyObj) {
    if (!selectedOpp) return;
    const key = personKey(person.name);
    setLoadingEmail(key);
    setRetryMsg(null);
    try {
      const data = await callApi(
        "person-contact",
        { person, opportunity: selectedOpp },
        (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setEmailByPerson((current) => ({ ...current, [key]: data }));
      mergeLibraryEmail(person, data);
    } catch (err: any) {
      setEmailByPerson((current) => ({
        ...current,
        [key]: { __error: err?.message || "Email lookup failed" },
      }));
    } finally {
      setLoadingEmail(null);
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
      setOppByAngle((current) => ({ ...current, [angleKey(angle)]: data }));
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
      setOppByAngle((current) => ({ ...current, [angleKey(selectedAngle)]: data }));
    } catch (err: any) {
      setErrOpp(err?.message || "Something went wrong");
    } finally {
      setLoadingOpp(false);
      setRetryMsg(null);
    }
  }

  async function researchAllAngles() {
    const angles = analysis?.pr_angles ?? [];
    if (angles.length === 0) return;
    if (!budgetAllows(angles.length)) return;
    if (!confirmBulk("Research all angles", angles.length)) return;
    setLoadingOpp(true);
    setErrOpp(null);
    setRetryMsg(null);
    const failures: string[] = [];
    try {
      for (let index = 0; index < angles.length; index += 1) {
        const angle = angles[index];
        setRetryMsg(`Researching angles ${index + 1} of ${angles.length}...`);
        try {
          const data = await callApi("opportunities", { angle }, (attempt) =>
            setRetryMsg(`Researching angles ${index + 1} of ${angles.length} - retry ${attempt}/3...`)
          );
          setOppByAngle((current) => ({ ...current, [angleKey(angle)]: data }));
          if (angleKey(angle) === angleKey(selectedAngle)) setOpportunities(data);
        } catch (err: any) {
          failures.push(`${shortText(angle.angle, 60)}: ${err?.message || "failed"}`);
          if (String(err?.message || "").match(/429|limit|budget|Too many/i)) break;
        }
      }
      if (failures.length > 0) {
        setErrOpp(`Stopped with ${failures.length} failure(s). ${failures.join(" | ")}`);
      }
    } finally {
      setLoadingOpp(false);
      setRetryMsg(null);
    }
  }

  async function researchJournalistsFor(opportunity: AnyObj) {
    if (!selectedAngle) return;
    setSelectedOpp(opportunity);
    setJournalists(null);
    setCheckedPeople([]);
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
      setWritersByOpp((current) => ({ ...current, [oppKey(opportunity)]: data }));
      saveToLibrary(data?.journalists, opportunity, selectedAngle);
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
    setCheckedPeople([]);
    setRetryMsg(null);
    try {
      const data = await callApi(
        "journalists",
        { angle: selectedAngle, opportunity: selectedOpp },
        (a) => setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setJournalists(data);
      setWritersByOpp((current) => ({ ...current, [oppKey(selectedOpp)]: data }));
      saveToLibrary(data?.journalists, selectedOpp, selectedAngle);
    } catch (err: any) {
      setErrJourn(err?.message || "Something went wrong");
    } finally {
      setLoadingJourn(false);
      setRetryMsg(null);
    }
  }

  async function findWritersForAll() {
    const opps = opportunities?.opportunities ?? [];
    if (!selectedAngle || opps.length === 0) return;
    if (!budgetAllows(opps.length)) return;
    if (!confirmBulk("Find writers for all", opps.length)) return;
    setLoadingJourn(true);
    setErrJourn(null);
    setCheckedPeople([]);
    setRetryMsg(null);
    const failures: string[] = [];
    const collected: Record<string, AnyObj> = {};
    try {
      for (let index = 0; index < opps.length; index += 1) {
        const opportunity = opps[index];
        setRetryMsg(`Finding writers ${index + 1} of ${opps.length}...`);
        try {
          const data = await callApi(
            "journalists",
            { angle: selectedAngle, opportunity },
            (attempt) => setRetryMsg(`Finding writers ${index + 1} of ${opps.length} - retry ${attempt}/3...`)
          );
          collected[oppKey(opportunity)] = data;
          setWritersByOpp((current) => ({ ...current, [oppKey(opportunity)]: data }));
          saveToLibrary(data?.journalists, opportunity, selectedAngle);
          if (oppKey(opportunity) === oppKey(selectedOpp)) setJournalists(data);
        } catch (err: any) {
          failures.push(`${shortText(opportunity.article_title, 60)}: ${err?.message || "failed"}`);
          if (String(err?.message || "").match(/429|limit|budget|Too many/i)) break;
        }
      }
      if (failures.length > 0) {
        setErrJourn(`Stopped with ${failures.length} failure(s). ${failures.join(" | ")}`);
      }
      // Land on real results: select an opportunity that actually has writers.
      const firstWithWriters =
        opps.find((o: AnyObj) => (collected[oppKey(o)]?.journalists ?? []).length > 0) ?? opps[0];
      if (firstWithWriters) {
        setSelectedOpp(firstWithWriters);
        setJournalists(collected[oppKey(firstWithWriters)] ?? writersByOpp[oppKey(firstWithWriters)] ?? null);
      }
      setDigitalStep("Journalists");
    } finally {
      setLoadingJourn(false);
      setRetryMsg(null);
    }
  }

  function markUrlsUsed(urls: ArrayLike<any>) {
    const norms = Array.from(urls)
      .map((u) => normalizeUrl(u))
      .filter(Boolean);
    if (norms.length === 0) return;
    setUsedUrls((current) => {
      const next = [...current];
      for (const u of norms) {
        if (!next.includes(u)) next.push(u);
      }
      return next;
    });
  }

  async function writeDraft(person: AnyObj) {
    if (!selectedAngle || !selectedOpp) return;
    const key = draftKey(oppKey(selectedOpp), person.name);
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
      markUrlsUsed([oppKey(selectedOpp)]);
      setDigitalStep("Outreach");
    } catch (err: any) {
      setErrDraft(err?.message || "Draft generation failed");
    } finally {
      setLoadingDraft(null);
      setRetryMsg(null);
    }
  }

  async function writeAllPitches() {
    const entries: Array<{ angle: AnyObj; opportunity: AnyObj; person: AnyObj }> = [];
    for (const [key, res] of Object.entries(oppByAngle)) {
      const angle = (analysis?.pr_angles ?? []).find((a: AnyObj) => angleKey(a) === key);
      if (!angle) continue;
      for (const opportunity of res?.opportunities ?? []) {
        for (const person of writersByOpp[oppKey(opportunity)]?.journalists ?? []) {
          entries.push({ angle, opportunity, person });
        }
      }
    }
    if (entries.length === 0) return;
    await runPitchBatch(entries);
  }

  async function writeSelectedPitches() {
    if (!selectedAngle || !selectedOpp || checkedPeople.length === 0) return;
    const people = (journalists?.journalists ?? []).filter((j: AnyObj) =>
      checkedPeople.includes(String(j.name || ""))
    );
    if (people.length === 0) return;
    await runPitchBatch(
      people.map((person: AnyObj) => ({
        angle: selectedAngle,
        opportunity: selectedOpp,
        person,
      }))
    );
  }

  async function runPitchBatch(
    entries: Array<{ angle: AnyObj; opportunity: AnyObj; person: AnyObj }>
  ) {
    if (!budgetAllows(entries.length)) return;
    if (!confirmBulk("Write all pitches", entries.length)) return;
    setLoadingDraft("__all__");
    setErrDraft(null);
    setRetryMsg(null);
    const failures: string[] = [];
    let done = 0;
    const pitchedUrls: string[] = [];
    try {
      for (let index = 0; index < entries.length; index += 1) {
        const { angle, opportunity, person } = entries[index];
        const key = draftKey(oppKey(opportunity), person.name);
        setRetryMsg(`Writing pitches ${index + 1} of ${entries.length}...`);
        try {
          const data = await callApi(
            "draft",
            { angle, opportunity, person },
            (attempt) => setRetryMsg(`Writing pitches ${index + 1} of ${entries.length} - retry ${attempt}/3...`)
          );
          setDrafts((current) => ({ ...current, [key]: data }));
          pitchedUrls.push(oppKey(opportunity));
          done += 1;
        } catch (err: any) {
          failures.push(`${shortText(person.name, 40)}: ${err?.message || "failed"}`);
          if (String(err?.message || "").match(/429|limit|budget|Too many/i)) break;
        }
      }
      if (failures.length > 0) {
        setErrDraft(
          `Wrote ${done} of ${entries.length} pitches. Failures: ${failures.join(" | ")}`
        );
      }
      markUrlsUsed(pitchedUrls);
      if (done > 0) setDigitalStep("Outreach");
      void refreshQuota();
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
    const angleGroups: Array<[string, AnyObj | null]> =
      Object.entries(oppByAngle).length > 0
        ? Object.entries(oppByAngle)
        : [[angleKey(selectedAngle), opportunities]];
    const header = [
      "angle",
      "publication",
      "site_domain",
      "article_title",
      "article_url",
      "used",
      "pr_fit",
      "pr_score",
      "pr_score_reasons",
      "dr",
      "audience_question",
      "aeo_answer",
      "aeo_format",
      "aeo_schema",
      "contact_name",
      "contact_role",
      "subject",
      "body",
      "outcome",
      "coverage_url",
    ];
    const rows: string[][] = [];
    for (const [angleName, res] of angleGroups) {
      for (const opportunity of res?.opportunities ?? []) {
        const writers = writersByOpp[oppKey(opportunity)]?.journalists ?? [];
        const contacts = writers.length ? writers : [null];
        for (const person of contacts) {
          const draft = person ? drafts[draftKey(oppKey(opportunity), person.name)] : null;
          let domain = "";
          try {
            domain = new URL(opportunity.article_url || "").hostname.replace(/^www\./, "");
          } catch {
            domain = "";
          }
          rows.push([
            angleName || "",
            opportunity.publication || "",
            domain,
            opportunity.article_title || "",
            opportunity.article_url || "",
            isUsed(opportunity.article_url) ? "yes" : "no",
            opportunity.pr_fit || "",
            opportunity.pr_score || "",
            Array.isArray(opportunity.pr_score_reasons)
              ? opportunity.pr_score_reasons.join("; ")
              : "",
            (() => {
              let domain = "";
              try {
                domain = new URL(opportunity.article_url || "").hostname.replace(/^www\./, "").toLowerCase();
              } catch {
                domain = "";
              }
              return drByDomain[domain] ?? "";
            })(),
            opportunity.audience_question || "",
            opportunity.aeo_answer || "",
            opportunity.aeo_format || "",
            opportunity.aeo_schema || "",
            person?.name || "",
            person?.current_role || "",
            draft?.subject_line || "",
            draft?.message_body || "",
            (() => {
              const id = draftKey(oppKey(opportunity), person?.name);
              return pitchOutcomes[id]?.status || (draft ? "Draft" : "");
            })(),
            (() => {
              const id = draftKey(oppKey(opportunity), person?.name);
              return pitchOutcomes[id]?.coverage_url || "";
            })(),
          ]);
        }
      }
    }
    const csv = [header, ...rows]
      .map((row) => row.map(csvCell).join(","))
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

  async function runContact(item: AnyObj, force = false) {
    setSelectedItem(item);
    const cached = contactByItem[item.listicle_url];
    // Instant when already researched: show the cache, Refresh forces a new call.
    if (cached && !force) {
      setContact(cached);
      setErrContact(null);
      return;
    }
    setLoadingContact(true);
    setErrContact(null);
    setContact(null);
    setRetryMsg(null);
    try {
      const data = await callApi("listicle-contact", { item }, (a) =>
        setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setContact(data);
      setContactByItem((current) => ({ ...current, [item.listicle_url]: data }));
    } catch (err: any) {
      setErrContact(err?.message || "Something went wrong");
    } finally {
      setLoadingContact(false);
      setRetryMsg(null);
    }
  }

  async function runPolicy(item: AnyObj, force = false) {
    setSelectedItem(item);
    const cached = policyByItem[item.listicle_url];
    if (cached && !force) {
      setPolicy(cached);
      setErrPolicy(null);
      return;
    }
    setLoadingPolicy(true);
    setErrPolicy(null);
    setPolicy(null);
    setRetryMsg(null);
    try {
      const data = await callApi("publisher-policy", { item }, (a) =>
        setRetryMsg(`Retrying (attempt ${a}/3)...`)
      );
      setPolicy(data);
      setPolicyByItem((current) => ({ ...current, [item.listicle_url]: data }));
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
        {quota && typeof quota.remaining === "number" && (
          <div>
            Calls left today: <strong>{quota.remaining}</strong>
          </div>
        )}
        {syncErr && (
          <div className="sidebar-note">
            Sheet sync failed. Open Outreach or Settings to retry.
          </div>
        )}
        {quota && quota.remaining === 0 && (
          <div className="sidebar-note">
            Daily research limit reached. It resets tomorrow.
          </div>
        )}
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
                  <div className="actions" style={{ marginTop: 0 }}>
                    <button
                      className="btn-secondary"
                      onClick={saveCampaign}
                      disabled={!analysis && Object.keys(drafts).length === 0}
                      title="Save this workspace as a named campaign on the board"
                    >
                      Save as campaign
                    </button>
                    <button className="btn-secondary" onClick={() => setShowStart(true)}>
                      ← Back to start
                    </button>
                  </div>
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
              {workflow === "digital" && stepsOfDigitalPhase[activePhase as DigitalPhase].length > 1 && (
                <div className="stepper" role="tablist" aria-label="Steps in this phase">
                  {stepsOfDigitalPhase[activePhase as DigitalPhase].map((step) => (
                    <button
                      key={step}
                      role="tab"
                      aria-selected={digitalStep === step}
                      className={digitalStep === step ? "active" : ""}
                      onClick={() => setDigitalStep(step)}
                    >
                      {step}
                    </button>
                  ))}
                </div>
              )}

              {retryMsg && <Note>{retryMsg}</Note>}

              {workflow === "digital" && activePhase === "Research" && digitalStep === "Article" && (
                <div className="stack">
                  <section className="card">
                    <h2 className="section-title">Scan a domain</h2>
                    <p className="body-text">
                      Enter a publication domain to find its recent articles ranked by PR-pitch
                      suitability. Pick one to analyze it and build angles from it.
                    </p>
                    <form onSubmit={scanDomain} style={{ marginTop: 16 }}>
                      <div className="form-grid">
                        <div className="field">
                          <label htmlFor="scan-domain">Domain</label>
                          <input
                            id="scan-domain"
                            type="text"
                            value={domainInput}
                            onChange={(e) => setDomainInput(e.target.value)}
                            placeholder="example.com"
                            aria-label="Publication domain"
                            className="input"
                          />
                        </div>
                        <div className="field">
                          <label htmlFor="scan-topic">Topic focus (optional)</label>
                          <input
                            id="scan-topic"
                            type="text"
                            value={topicHint}
                            onChange={(e) => setTopicHint(e.target.value)}
                            placeholder="e.g. social media analytics"
                            aria-label="Optional topic focus"
                            className="input"
                          />
                        </div>
                      </div>
                      <div className="actions" style={{ marginTop: 10 }}>
                        <button type="submit" disabled={loadingScan} className="btn-primary">
                          {loadingScan ? <Spinner /> : <Search size={17} />}
                          {loadingScan ? "Scanning domain..." : "Scan domain"}
                        </button>
                      </div>
                    </form>
                    <p className="meta" style={{ marginTop: 8 }}>
                      One research call per scan. Results rank Strong fit first.
                    </p>
                    {errScan && <Note tone="warn">{errScan}</Note>}
                    {scanResult && (
                      <div className="stack-sm" style={{ marginTop: 14 }}>
                        <p className="step-caption">
                          {scanResult.publication_name} · {scanResult.research_summary}
                        </p>
                        <div className="actions" style={{ marginTop: 0 }}>
                          <button
                            className="btn-primary"
                            onClick={analyzeSelectedScan}
                            disabled={loadingAnalyze || selectedScan.length === 0}
                            title="Analyze every ticked article at once (up to 5)"
                          >
                            {loadingAnalyze && analyzingUrl === "__bulk__" ? (
                              <Spinner />
                            ) : (
                              <Search size={16} />
                            )}
                            {selectedScan.length > 0
                              ? `Analyze selected (${Math.min(selectedScan.length, 5)})`
                              : "Tick articles, then analyze"}
                          </button>
                          <button
                            className="btn-secondary"
                            onClick={() =>
                              checkDr((scanResult.articles ?? []).map((a: AnyObj) => a.article_url))
                            }
                            disabled={loadingDr}
                            title="Look up Ahrefs Domain Rating for these sites (1 research call)"
                          >
                            {loadingDr ? <Spinner /> : <BarChart3 size={16} />}
                            {loadingDr ? "Checking DR..." : "Check DR"}
                          </button>
                          <label className="meta" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <input
                              type="checkbox"
                              checked={drOnly}
                              onChange={(e) => setDrOnly(e.target.checked)}
                            />
                            DR {DR_CUTOFF}+ only
                          </label>
                        </div>
                        {sortByScore(
                          filterProspects(
                            scanResult.articles ?? [],
                            (a: AnyObj) => a.article_url
                          ).visible
                        ).map((a: AnyObj, i: number) => (
                          <article className="card" key={`${a.article_url}-${i}`}>
                            <div className="card-head">
                              <div>
                                <h2 className="card-title">
                                  {a.article_title} {isUsed(a.article_url) && <UsedBadge />}{" "}
                                  <DrBadge url={a.article_url} />
                                </h2>
                                <p className="meta">
                                  {a.topic} · {a.published_date}
                                </p>
                              </div>
                              {a.article_url?.startsWith("https://") && (
                                <SafeA className="btn-secondary" url={a.article_url}>
                                  Open article <ExternalLink size={15} />
                                </SafeA>
                              )}
                            </div>
                            <p className="body-text">
                              <strong>Why it matters:</strong> {shortText(a.why_pitchable)}
                            </p>
                            <ScoreLine item={a} />
                            {a.suggested_angle && (
                              <p className="body-text">
                                <strong>Suggested angle:</strong> {shortText(a.suggested_angle)}
                              </p>
                            )}
                            {a.pr_fit && fitStyles[a.pr_fit] && (
                              <div className={`fit-banner ${fitStyles[a.pr_fit].className}`}>
                                <strong>{fitStyles[a.pr_fit].label}</strong>
                                <span>{a.pr_fit_reason}</span>
                              </div>
                            )}
                            {Array.isArray(a.pr_red_flags) && a.pr_red_flags.length > 0 && (
                              <p className="meta">Signals: {a.pr_red_flags.join(" · ")}</p>
                            )}
                            <div className="actions">
                              <label
                                className="meta"
                                style={{ display: "flex", gap: 8, alignItems: "center", cursor: "pointer" }}
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedScan.includes(a.article_url)}
                                  onChange={() => toggleScan(a.article_url)}
                                  aria-label={`Select ${a.article_title}`}
                                />
                                Select
                              </label>
                              <button
                                className="btn-primary"
                                onClick={() => useScannedArticle(a.article_url)}
                                disabled={loadingAnalyze}
                              >
                                {loadingAnalyze && analyzingUrl === a.article_url ? (
                                  <>
                                    <Spinner /> Analyzing...
                                  </>
                                ) : (
                                  <>
                                    Analyze this article <ArrowRight size={16} />
                                  </>
                                )}
                              </button>
                              <UsedToggle url={a.article_url} />
                            </div>
                          </article>
                        ))}
                        {(() => {
                          const f = filterProspects(
                            scanResult.articles ?? [],
                            (a: AnyObj) => a.article_url
                          );
                          return (
                            <FilterNotes
                              hiddenUsed={f.hiddenUsed}
                              hiddenDr={f.hiddenDr}
                              drKnown={f.drKnown}
                            />
                          );
                        })()}
                        {(!scanResult.articles || scanResult.articles.length === 0) && (
                          <Note tone="warn">No usable articles were found on this domain.</Note>
                        )}
                      </div>
                    )}
                  </section>
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

              {workflow === "digital" && activePhase === "Research" && digitalStep === "PR angles" && !!analysis && (
                <>
                  <p className="step-caption">
                    Research one angle, or research them all at once. Each angle keeps its own results.
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
                      <div className="actions">
                        <button className="btn-primary" onClick={researchAllAngles} disabled={loadingOpp}>
                          {loadingOpp ? <Spinner /> : <Search size={17} />}
                          {loadingOpp ? "Researching all angles..." : "Research all angles at once"}
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
                              onClick={() => pickAngle(a)}
                            >
                              {loadingOpp && selectedAngle?.angle === a.angle ? (
                                <>
                                  <Spinner /> Researching angle...
                                </>
                              ) : oppByAngle[angleKey(a)] ? (
                                <>
                                  Researched ✓ — view opportunities <ArrowRight size={16} />
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

              {workflow === "digital" && activePhase === "Prospects" && digitalStep === "Opportunities" && (
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
                      <div className="actions" style={{ marginTop: 0 }}>
                        {(analysis?.pr_angles ?? []).map((a: AnyObj, i: number) => (
                          <button
                            key={`${a.angle}-${i}`}
                            type="button"
                            className={angleKey(a) === angleKey(selectedAngle) ? "btn-primary" : "btn-secondary"}
                            onClick={() => pickAngle(a)}
                            title={shortText(a.angle, 120)}
                          >
                            {i + 1}. {shortText(a.angle, 32)} {oppByAngle[angleKey(a)] ? "✓" : ""}
                          </button>
                        ))}
                      </div>
                      <section className="context-card">
                        <span className="context-label">Selected angle</span>
                        <span className="context-value">{selectedAngle.angle}</span>
                      </section>

                      <div className="actions-between">
                        <button className="btn-primary" onClick={runOpportunities} disabled={loadingOpp}>
                          {loadingOpp ? <Spinner /> : opportunities ? <RefreshCw size={17} /> : <Search size={17} />}
                          {opportunities ? "Generate again" : "Run opportunity research"}
                        </button>
                        {opportunities && (opportunities.opportunities ?? []).length > 1 && (
                          <button className="btn-secondary" onClick={findWritersForAll} disabled={loadingJourn}>
                            {loadingJourn ? <Spinner /> : <Users size={17} />}
                            {loadingJourn ? "Finding writers..." : "Find writers for all"}
                          </button>
                        )}
                        {opportunities && (opportunities.opportunities ?? []).length > 0 && (
                          <button
                            className="btn-secondary"
                            onClick={() =>
                              checkDr((opportunities.opportunities ?? []).map((o: AnyObj) => o.article_url))
                            }
                            disabled={loadingDr}
                            title="Look up Ahrefs Domain Rating for these sites (1 research call)"
                          >
                            {loadingDr ? <Spinner /> : <BarChart3 size={17} />}
                            {loadingDr ? "Checking DR..." : "Check DR"}
                          </button>
                        )}
                      </div>

                      {errOpp && <Note tone="warn">{errOpp}</Note>}

                      {opportunities && (
                        <>
                          <p className="step-caption">{opportunities.research_summary}</p>
                          {Object.keys(drByDomain).length > 0 && (
                            <p className="meta">DR badges: Domain Rating by Ahrefs.</p>
                          )}
                          {usedUrls.length > 0 && (
                            <label className="meta" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                              <input
                                type="checkbox"
                                checked={hideUsed}
                                onChange={(e) => setHideUsed(e.target.checked)}
                              />
                              Hide used ({usedUrls.length} marked)
                            </label>
                          )}
                          <label className="meta" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <input
                              type="checkbox"
                              checked={drOnly}
                              onChange={(e) => setDrOnly(e.target.checked)}
                            />
                            DR {DR_CUTOFF}+ only
                          </label>
                          {sortByScore(
                            filterProspects(
                              opportunities.opportunities ?? [],
                              (o: AnyObj) => o.article_url
                            ).visible
                          ).map((o: AnyObj, i: number) => (                            <article className="card" key={`${o.article_url}-${i}`}>
                              <div className="card-head">
                                <div>
                                  <h2 className="card-title">
                                    {o.article_title} {isUsed(o.article_url) && <UsedBadge />}{" "}
                                    <DrBadge url={o.article_url} />
                                  </h2>
                                  <p className="meta">
                                    {o.publication} · {o.published_date} · {o.opportunity_type}
                                  </p>
                                </div>
                                {o.article_url?.startsWith("https://") && (
                                  <SafeA className="btn-secondary" url={o.article_url}>Open article <ExternalLink size={15} /></SafeA>
                                )}
                              </div>
                              <p className="body-text">
                                <strong>Why it matters:</strong> {shortText(o.why_relevant)}
                              </p>
                              <ScoreLine item={o} />
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
                                <UsedToggle url={o.article_url} />
                              </div>
                            </article>
                          ))}
                          {(() => {
                            const f = filterProspects(
                              opportunities.opportunities ?? [],
                              (o: AnyObj) => o.article_url
                            );
                            return (
                              <FilterNotes
                                hiddenUsed={f.hiddenUsed}
                                hiddenDr={f.hiddenDr}
                                drKnown={f.drKnown}
                              />
                            );
                          })()}
                          {(!opportunities.opportunities || opportunities.opportunities.length === 0) && (
                            <Note tone="warn">No suitable opportunity was verified for this angle.</Note>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </>
              )}

              {workflow === "digital" && activePhase === "Prospects" && digitalStep === "Journalists" && (
                <>
                  <p className="step-caption">
                    Find writers or the best content/SEO contact for each opportunity, then write all pitches at once.
                  </p>
                  {!selectedAngle || !selectedOpp ? (
                    <div className="card empty-state">
                      <h2 className="empty-title">
                        {selectedAngle && (opportunities?.opportunities ?? []).length > 0
                          ? "Choose an opportunity"
                          : "Pick an opportunity first"}
                      </h2>
                      {selectedAngle && (opportunities?.opportunities ?? []).length > 0 ? (
                        <>
                          <p className="empty-copy">
                            Writers are kept per opportunity. Pick one to see who was found.
                          </p>
                          <div className="actions" style={{ justifyContent: "center" }}>
                            {(opportunities?.opportunities ?? []).slice(0, 6).map((o: AnyObj, i: number) => (
                              <button
                                key={`${o.article_url}-${i}`}
                                className="btn-secondary"
                                onClick={() => selectOppCached(o)}
                                title={shortText(o.article_title, 100)}
                              >
                                {i + 1}. {shortText(o.article_title, 28)}{" "}
                                {writersByOpp[oppKey(o)] ? "✓" : ""}
                              </button>
                            ))}
                          </div>
                        </>
                      ) : (
                        <button className="btn-secondary" onClick={() => setDigitalStep("Opportunities")}>
                          Go to Opportunities
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="stack">
                      <div className="actions" style={{ marginTop: 0 }}>
                        {(opportunities?.opportunities ?? []).map((o: AnyObj, i: number) => (
                          <button
                            key={`${o.article_url}-${i}`}
                            type="button"
                            className={oppKey(o) === oppKey(selectedOpp) ? "btn-primary" : "btn-secondary"}
                            onClick={() => selectOppCached(o)}
                            title={shortText(o.article_title, 120)}
                          >
                            {i + 1}. {shortText(o.article_title, 32)} {writersByOpp[oppKey(o)] ? "✓" : ""}
                          </button>
                        ))}
                      </div>
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
                        <button
                          className="btn-primary"
                          onClick={writeSelectedPitches}
                          disabled={loadingDraft !== null || checkedPeople.length === 0}
                          title="Write pitches only for the people you ticked"
                        >
                          {loadingDraft !== null ? <Spinner /> : <Mail size={17} />}
                          {checkedPeople.length > 0
                            ? `Write pitches for selected (${checkedPeople.length})`
                            : "Tick people, then write"}
                        </button>
                        <button
                          className="btn-secondary"
                          onClick={writeAllPitches}
                          disabled={loadingDraft !== null || writerEntries.length === 0}
                          title="Write a pitch for every researched writer across all angles"
                        >
                          {loadingDraft === "__all__" ? <Spinner /> : <Mail size={17} />}
                          {loadingDraft === "__all__" ? "Writing all..." : "Write all pitches"}
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
                                      <SafeA url={j.relevant_article_url}>Open coverage <ExternalLink size={13} className="inline" /></SafeA>
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
                                <label
                                  className="meta"
                                  style={{ display: "flex", gap: 8, alignItems: "center", cursor: "pointer" }}
                                >
                                  <input
                                    type="checkbox"
                                    checked={checkedPeople.includes(String(j.name || ""))}
                                    onChange={() => togglePerson(j.name)}
                                    aria-label={`Select ${j.name} for pitching`}
                                  />
                                  Select
                                </label>
                                <button
                                  className="btn-primary"
                                  onClick={() => writeDraft(j)}
                                  disabled={loadingDraft === draftKey(oppKey(selectedOpp), j.name)}
                                >
                                  {loadingDraft === draftKey(oppKey(selectedOpp), j.name) ? (
                                    <>
                                      <Spinner /> Writing pitch...
                                    </>
                                  ) : drafts[draftKey(oppKey(selectedOpp), j.name)] ? (
                                    <>
                                      Write again <RefreshCw size={15} />
                                    </>
                                  ) : (
                                    <>
                                      Write pitch <ArrowRight size={15} />
                                    </>
                                  )}
                                </button>
                                <button
                                  className="btn-secondary"
                                  onClick={() => findEmailFor(j)}
                                  disabled={loadingEmail === personKey(j.name)}
                                  title="Look up this person's publicly published email"
                                >
                                  {loadingEmail === personKey(j.name) ? (
                                    <Spinner />
                                  ) : (
                                    <Mail size={15} />
                                  )}
                                  {emailByPerson[personKey(j.name)] && !emailByPerson[personKey(j.name)].__error
                                    ? "Refresh email"
                                    : "Find email"}
                                </button>
                              </div>
                              {emailByPerson[personKey(j.name)] && (
                                <div className="inline-panel">
                                  {emailByPerson[personKey(j.name)].__error ? (
                                    <Note tone="warn">{emailByPerson[personKey(j.name)].__error}</Note>
                                  ) : (
                                    <>
                                      <p className="result-copy">
                                        <strong>Email:</strong>{" "}
                                        {emailByPerson[personKey(j.name)].email || "Not publicly found"}
                                      </p>
                                      {emailByPerson[personKey(j.name)].contact_page_url &&
                                        emailByPerson[personKey(j.name)].contact_page_url !== "Unknown" && (
                                          <p className="result-copy">
                                            <strong>Contact route:</strong>{" "}
                                            <SafeA url={emailByPerson[personKey(j.name)].contact_page_url}>
                                              {emailByPerson[personKey(j.name)].route || "Open contact page"}{" "}
                                              <ExternalLink size={13} className="inline" />
                                            </SafeA>
                                          </p>
                                        )}
                                      {emailByPerson[personKey(j.name)].evidence && (
                                        <p className="result-meta">
                                          {shortText(emailByPerson[personKey(j.name)].evidence, 220)}
                                        </p>
                                      )}
                                    </>
                                  )}
                                </div>
                              )}
                              {drafts[draftKey(oppKey(selectedOpp), j.name)] && (
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
                      Personalized drafts for every researched contact. Copy or download them; nothing is sent.
                      {Object.keys(drafts).length > 0 &&
                        ` · ${outcomeCounts["Pitched"] || 0} pitched · ${outcomeCounts["Replied"] || 0} replied · ${outcomeCounts["Covered"] || 0} covered`}
                    </p>
                    {(() => {
                      const people = journalists?.journalists ?? [];
                      const nextPerson = people.find(
                        (p: AnyObj) => !drafts[draftKey(oppKey(selectedOpp), p.name)]
                      );
                      if (people.length === 0) return null;
                      return (
                        <>
                          {nextPerson && (
                            <button
                              className="btn-primary"
                              onClick={() => writeDraft(nextPerson)}
                              disabled={loadingDraft !== null}
                              title={`Write the pitch for ${nextPerson.name}`}
                            >
                              {loadingDraft ? <Spinner /> : <ArrowRight size={16} />}
                              {loadingDraft
                                ? "Writing..."
                                : `Write next pitch (${shortText(nextPerson.name, 22)})`}
                            </button>
                          )}
                          <button
                            className="btn-secondary"
                            onClick={() => setDigitalStep("Journalists")}
                          >
                            ← Back to contacts
                          </button>
                        </>
                      );
                    })()}
                    {Object.keys(drafts).length > 0 && (
                      <button
                        className="btn-secondary"
                        onClick={() =>
                          navigator.clipboard.writeText(
                            Object.entries(drafts)
                              .map(
                                ([name, d]) =>
                                  `To: ${d.recipient_name || name} (${d.publication || ""})\nSubject: ${d.subject_line}\n\n${d.message_body}`
                              )
                              .join("\n\n---\n\n")
                          )
                        }
                      >
                        <Copy size={15} /> Copy all
                      </button>
                    )}
                    <button className="btn-secondary" onClick={downloadCampaignCsv}>
                      Download CSV <Download size={15} />
                    </button>
                    {Object.keys(drafts).length > 0 && (
                      <button
                        className="btn-primary"
                        onClick={() => syncToSheet()}
                        disabled={syncing}
                        title="Add or refresh every pitch in the connected Google Sheet"
                      >
                        {syncing ? <Spinner /> : <Server size={17} />}
                        {syncing ? "Syncing..." : "Sync to Google Sheet"}
                      </button>
                    )}
                    <label className="meta" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input
                        type="checkbox"
                        checked={autoSync}
                        onChange={(e) => setAutoSync(e.target.checked)}
                      />
                      Auto-sync
                    </label>
                  </div>

                  {Object.keys(drafts).length > 0 && (
                    <div className="card">
                      <div className="card-head">
                        <div>
                          <h2 className="section-title" style={{ fontSize: "1.05rem" }}>
                            Batch update
                          </h2>
                          <p className="meta">
                            {selectedDrafts.length === 0
                              ? "Tick drafts below, then set the same status in one click."
                              : `${selectedDrafts.length} selected`}
                          </p>
                        </div>
                        <button
                          className="btn-secondary"
                          onClick={() => toggleAllDrafts(Object.keys(drafts))}
                        >
                          {selectedDrafts.length === Object.keys(drafts).length ? "Clear all" : "Select all"}
                        </button>
                      </div>
                      <div className="actions" style={{ marginTop: 12 }}>
                        {["Pitched", "Replied", "Covered", "Declined", "Do not contact"].map((s) => (
                          <button
                            key={s}
                            className={s === "Covered" ? "btn-primary" : "btn-secondary"}
                            onClick={() => bulkStatus(s)}
                            disabled={selectedDrafts.length === 0}
                          >
                            Mark {s}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {errDraft && <Note tone="warn">{errDraft}</Note>}
                  {syncErr && <Note tone="warn">{syncErr}</Note>}
                  {syncMsg && <Note>{syncMsg}</Note>}

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
                        <div className="card-head">
                          <div>
                            <h2 className="card-title">{draft.recipient_name || name}</h2>
                            <p className="meta">
                              {draft.publication} · {draft.recipient_role} · {draft.channel}
                            </p>
                          </div>
                          <span
                            className={`status-pill ${(pitchOutcomes[name]?.status || "Draft") !== "Draft" ? "active" : ""}`}
                          >
                            {pitchOutcomes[name]?.status || "Draft"}
                          </span>
                          <label
                            className="meta"
                            style={{ display: "flex", gap: 6, alignItems: "center", whiteSpace: "nowrap" }}
                          >
                            <input
                              type="checkbox"
                              checked={selectedDrafts.includes(name)}
                              onChange={() => toggleDraftSel(name)}
                              aria-label={`Select ${draft.recipient_name || name}`}
                            />
                            Select
                          </label>
                        </div>
                        <div className="form-row">
                          <div className="field">
                            <label htmlFor={`outcome-${name}`}>Outcome</label>
                            <select
                              id={`outcome-${name}`}
                              className="input"
                              value={pitchOutcomes[name]?.status || "Draft"}
                              onChange={(e) => setOutcome(name, { status: e.target.value })}
                            >
                              {["Draft", "Pitched", "Replied", "Covered", "Declined", "Do not contact"].map((s) => (
                                <option key={s} value={s}>
                                  {s}
                                </option>
                              ))}
                            </select>
                          </div>
                          {(pitchOutcomes[name]?.status === "Covered" ||
                            pitchOutcomes[name]?.coverage_url) && (
                            <div className="field">
                              <label htmlFor={`coverage-${name}`}>Coverage URL</label>
                              <input
                                id={`coverage-${name}`}
                                type="url"
                                className="input"
                                placeholder="https://..."
                                value={pitchOutcomes[name]?.coverage_url || ""}
                                onChange={(e) => setOutcome(name, { coverage_url: e.target.value })}
                              />
                            </div>
                          )}
                        </div>
                        {pitchOutcomes[name]?.status === "Covered" && pitchOutcomes[name]?.coverage_url?.startsWith("https://") && (
                          <p className="meta" style={{ marginTop: 8 }}>
                            Coverage:{" "}
                            <SafeA url={pitchOutcomes[name].coverage_url}>Open <ExternalLink size={12} className="inline" /></SafeA>
                          </p>
                        )}
                        <p className="body-text">
                          <strong>Subject:</strong> {draft.subject_line}
                        </p>
                        <div className="draft-body">{draft.message_body}</div>
                        {Array.isArray(draft.pitch_checks) && draft.pitch_checks.length > 0 && (
                          <details className="plan" open>
                            <summary>3-question check</summary>
                            <div className="plan-body">
                              {draft.pitch_checks.map((check: string, index: number) => (
                                <p key={index}>{check}</p>
                              ))}
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
                        <div className="actions" style={{ marginTop: 0 }}>
                          <button
                            className="btn-primary"
                            onClick={writeAllListicleDrafts}
                            disabled={loadingListDraft !== null}
                            title="Write an inclusion request for every contact you have researched"
                          >
                            {loadingListDraft === "__all__" ? <Spinner /> : <Mail size={16} />}
                            {loadingListDraft === "__all__"
                              ? "Writing requests..."
                              : `Write all inclusion requests (${Object.values(contactByItem).reduce(
                                  (n: number, c: AnyObj) => n + (c?.contacts?.length || 0),
                                  0
                                )})`}
                          </button>
                          <button
                            className="btn-secondary"
                            onClick={() => setListicleStep("Outreach")}
                            disabled={Object.keys(listicleDrafts).length === 0}
                          >
                            View requests ({Object.keys(listicleDrafts).length})
                          </button>
                          <button
                            className="btn-secondary"
                            onClick={() =>
                              checkDr((listicles.opportunities ?? []).map((x: AnyObj) => x.listicle_url))
                            }
                            disabled={loadingDr}
                            title="Look up Ahrefs Domain Rating for these sites (1 research call)"
                          >
                            {loadingDr ? <Spinner /> : <BarChart3 size={16} />}
                            {loadingDr ? "Checking DR..." : "Check DR"}
                          </button>
                          <label className="meta" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <input
                              type="checkbox"
                              checked={drOnly}
                              onChange={(e) => setDrOnly(e.target.checked)}
                            />
                            DR {DR_CUTOFF}+ only
                          </label>
                          <button
                            className="btn-secondary"
                            onClick={generateListicles}
                            disabled={loadingList || !listForm.search_theme.trim()}
                          >
                            {loadingList ? <Spinner /> : <RefreshCw size={16} />}
                            {loadingList ? "Generating again..." : "Generate again"}
                          </button>
                        </div>
                      </div>
                      {errListDraft && <Note tone="warn">{errListDraft}</Note>}
                      <Note>
                        Run <strong>Find contact</strong> on the listicles you want, then{" "}
                        <strong>Write all inclusion requests</strong> — it uses every researched contact at once.
                      </Note>
                      {sortByScore(
                        filterProspects(
                          listicles.opportunities ?? [],
                          (item: AnyObj) => item.listicle_url
                        ).visible
                      ).map((item: AnyObj, i: number) => (
                        <article className="card" key={`${item.listicle_url}-${i}`}>
                          <div className="card-head">
                            <div>
                              <h2 className="card-title">
                                {item.listicle_title} {isUsed(item.listicle_url) && <UsedBadge />}{" "}
                                <DrBadge url={item.listicle_url} />
                              </h2>
                              <p className="meta">
                                {item.publication} · {item.placement_type} · {item.published_or_updated}
                              </p>
                            </div>
                            {item.listicle_url?.startsWith("https://") && (
                              <SafeA className="btn-secondary" url={item.listicle_url}>Open page <ExternalLink size={15} /></SafeA>
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
                              {contactByItem[item.listicle_url] ? "View contact ✓" : "Find contact"}
                            </button>
                            <button
                              className="btn-secondary"
                              onClick={() => runPolicy(item)}
                              disabled={loadingPolicy}
                            >
                              {loadingPolicy && selectedItem === item ? <Spinner /> : <Shield size={16} />}
                              {policyByItem[item.listicle_url] ? "View policy ✓" : "Check policy"}
                            </button>
                            <UsedToggle url={item.listicle_url} />
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
                                        onClick={() => runContact(item, true)}
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
                                          <SafeA url={c.source_url}>Open source <ExternalLink size={13} className="inline" /></SafeA>
                                        )}
                                        <div className="actions" style={{ marginTop: 8 }}>
                                          <button
                                            className="btn-primary"
                                            onClick={() => writeListicleDraft(item, c)}
                                            disabled={loadingListDraft === listDraftKey(item.listicle_url, c.contact_name)}
                                          >
                                            {loadingListDraft === listDraftKey(item.listicle_url, c.contact_name) ? (
                                              <>
                                                <Spinner /> Writing request...
                                              </>
                                            ) : listicleDrafts[listDraftKey(item.listicle_url, c.contact_name)] ? (
                                              <>
                                                Write again <RefreshCw size={15} />
                                              </>
                                            ) : (
                                              <>
                                                Write inclusion request <ArrowRight size={15} />
                                              </>
                                            )}
                                          </button>
                                        </div>
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
                                        onClick={() => runPolicy(item, true)}
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
                                      <SafeA url={policy.policy_source_url}>Open policy source <ExternalLink size={13} className="inline" /></SafeA>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                        </article>
                      ))}
                      {(() => {
                        const f = filterProspects(
                          listicles.opportunities ?? [],
                          (item: AnyObj) => item.listicle_url
                        );
                        return (
                          <FilterNotes
                            hiddenUsed={f.hiddenUsed}
                            hiddenDr={f.hiddenDr}
                            drKnown={f.drKnown}
                          />
                        );
                      })()}
                      {(!listicles.opportunities || listicles.opportunities.length === 0) && (
                        <Note tone="warn">No listicle candidates were verified for this search.</Note>
                      )}
                    </div>
                  )}
                </>
              )}

              {workflow === "listicles" && listicleStep === "Outreach" && (
                <div className="stack">
                  <div className="actions-between">
                    <p className="step-caption">
                      Inclusion requests for the contacts you selected. Copy or download them; nothing is sent or
                      submitted.
                      {Object.keys(listicleDrafts).length > 0 &&
                        ` · ${Object.values(pitchOutcomes).filter((o: AnyObj) => o?.status === "Covered").length} covered`}
                    </p>
                    {Object.keys(listicleDrafts).length > 0 && (
                      <button
                        className="btn-secondary"
                        onClick={() =>
                          navigator.clipboard.writeText(
                            Object.entries(listicleDrafts)
                              .map(
                                ([, d]) =>
                                  `To: ${d.recipient_name || ""} (${(d.__item || {}).publication || d.publication || ""})\nSubject: ${d.subject_line}\n\n${d.message_body}`
                              )
                              .join("\n\n---\n\n")
                          )
                        }
                      >
                        <Copy size={15} /> Copy all
                      </button>
                    )}
                    {Object.keys(listicleDrafts).length > 0 && (
                      <button
                        className="btn-primary"
                        onClick={() => syncToSheet()}
                        disabled={syncing}
                      >
                        {syncing ? <Spinner /> : <Server size={17} />}
                        {syncing ? "Syncing..." : "Sync to Google Sheet"}
                      </button>
                    )}
                  </div>

                  {errListDraft && <Note tone="warn">{errListDraft}</Note>}
                  {syncErr && <Note tone="warn">{syncErr}</Note>}
                  {syncMsg && <Note>{syncMsg}</Note>}

                  {Object.keys(listicleDrafts).length === 0 ? (
                    <div className="card empty-state">
                      <div className="page-badge">Human approval</div>
                      <h2 className="empty-title">No inclusion requests yet</h2>
                      <p className="empty-copy">
                        Go to Prospects, run <strong>Find contact</strong> on a listicle, then click{" "}
                        <strong>Write inclusion request</strong>.
                      </p>
                      <button className="btn-secondary" onClick={() => setListicleStep("Prospects")}>
                        Back to Prospects
                      </button>
                    </div>
                  ) : (
                    Object.entries(listicleDrafts).map(([key, d]) => {
                      const item = d.__item || {};
                      const status = pitchOutcomes[key]?.status || "Draft";
                      return (
                        <article className="card" key={key}>
                          <div className="card-head">
                            <div>
                              <h2 className="card-title">{d.recipient_name || "Editorial team"}</h2>
                              <p className="meta">
                                {item.publication || d.publication} · {d.recipient_role} · {d.channel}
                              </p>
                              <p className="meta">{item.listicle_title || d.target_title}</p>
                            </div>
                            <span className={`status-pill ${status !== "Draft" ? "active" : ""}`}>{status}</span>
                          </div>
                          <p className="body-text">
                            <strong>Subject:</strong> {d.subject_line}
                          </p>
                          <div className="draft-body">{d.message_body}</div>
                          <div className="form-row">
                            <div className="field">
                              <label htmlFor={`lout-${key}`}>Outcome</label>
                              <select
                                id={`lout-${key}`}
                                className="input"
                                value={status}
                                onChange={(e) => setOutcome(key, { status: e.target.value })}
                              >
                                {["Draft", "Pitched", "Replied", "Covered", "Declined", "Do not contact"].map((s) => (
                                  <option key={s} value={s}>
                                    {s}
                                  </option>
                                ))}
                              </select>
                            </div>
                            {(status === "Covered" || pitchOutcomes[key]?.coverage_url) && (
                              <div className="field">
                                <label htmlFor={`lcov-${key}`}>Live listicle URL</label>
                                <input
                                  id={`lcov-${key}`}
                                  type="url"
                                  className="input"
                                  placeholder="https://..."
                                  value={pitchOutcomes[key]?.coverage_url || ""}
                                  onChange={(e) => setOutcome(key, { coverage_url: e.target.value })}
                                />
                              </div>
                            )}
                          </div>
                          <div className="actions">
                            <button
                              className="btn-secondary"
                              onClick={() =>
                                navigator.clipboard.writeText(
                                  `Subject: ${d.subject_line}\n\n${d.message_body}`
                                )
                              }
                            >
                              <Copy size={15} /> Copy
                            </button>
                            <button
                              className="btn-secondary"
                              onClick={() =>
                                downloadText(
                                  `listicle-${(d.recipient_name || "contact").replace(/\s+/g, "-").toLowerCase()}.txt`,
                                  `Subject: ${d.subject_line}\n\n${d.message_body}\n`
                                )
                              }
                            >
                              <Download size={15} /> Download
                            </button>
                            {item.listicle_url?.startsWith("https://") && (
                              <SafeA className="btn-secondary" url={item.listicle_url}>Open listicle <ExternalLink size={15} /></SafeA>
                            )}
                          </div>
                          <details className="plan">
                            <summary>Facts to verify</summary>
                            <div className="plan-body">
                              {(d.facts_to_verify ?? []).length > 0 ? (
                                (d.facts_to_verify ?? []).map((fact: string, index: number) => (
                                  <p key={index}>{fact}</p>
                                ))
                              ) : (
                                <p>None listed. Verify the contact and the inclusion route.</p>
                              )}
                              {d.compliance_notes && (
                                <p>
                                  <strong>Policy:</strong> {d.compliance_notes}
                                </p>
                              )}
                            </div>
                          </details>
                        </article>
                      );
                    })
                  )}
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

              <section className="card">
                <div className="card-head">
                  <div>
                    <h2 className="section-title">
                      Media library · {Object.keys(mediaLibrary).length} saved contacts
                    </h2>
                    <p className="meta">
                      Every researched writer is saved here automatically, with emails merged
                      from Find-email lookups. Stored in this browser.
                    </p>
                  </div>
                </div>
                <form onSubmit={collectWriters} style={{ marginTop: 16 }}>
                  <div className="field">
                    <label htmlFor="collect-query">Collect from the web</label>
                    <input
                      id="collect-query"
                      type="text"
                      value={collectQuery}
                      onChange={(e) => setCollectQuery(e.target.value)}
                      placeholder="e.g. SaaS reporters at The Verge, or writers covering social media analytics"
                      aria-label="What contacts to collect from the web"
                      className="input"
                    />
                    <span className="field-note">
                      One research call per collection. Only verifiable writers with real coverage are saved.
                    </span>
                  </div>
                  <div className="actions" style={{ marginTop: 10 }}>
                    <button type="submit" disabled={loadingCollect} className="btn-primary">
                      {loadingCollect ? <Spinner /> : <Search size={17} />}
                      {loadingCollect ? "Collecting..." : "Collect from web"}
                    </button>
                  </div>
                </form>
                {errCollect && <Note tone="warn">{errCollect}</Note>}
                {collectMsg && <Note>{collectMsg}</Note>}
                <div className="form-row">
                  <input
                    type="search"
                    value={libSearch}
                    onChange={(e) => setLibSearch(e.target.value)}
                    placeholder="Search name, outlet, beat, topic..."
                    aria-label="Search saved contacts"
                    className="input"
                  />
                </div>
                <div className="actions">
                  <label className="meta" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={libEmailOnly}
                      onChange={(e) => setLibEmailOnly(e.target.checked)}
                    />
                    Has email only
                  </label>
                  <button
                    className="btn-secondary"
                    onClick={() =>
                      downloadLibraryCsv(
                        Object.values(mediaLibrary).sort((a: AnyObj, b: AnyObj) =>
                          String(b.last_seen || "").localeCompare(String(a.last_seen || ""))
                        )
                      )
                    }
                    disabled={Object.keys(mediaLibrary).length === 0}
                  >
                    <Download size={15} /> Contacts CSV
                  </button>
                  <button
                    className="btn-primary"
                    onClick={syncContactsToSheet}
                    disabled={syncing || Object.keys(mediaLibrary).length === 0}
                    title="Sync the media library to the Contacts tab"
                  >
                    {syncing ? <Spinner /> : <Server size={17} />}
                    {syncing ? "Syncing..." : "Sync contacts"}
                  </button>
                  <button
                    className="btn-ghost"
                    onClick={() => {
                      if (window.confirm("Delete all saved contacts in this browser?")) {
                        setMediaLibrary({});
                      }
                    }}
                    disabled={Object.keys(mediaLibrary).length === 0}
                  >
                    Clear all
                  </button>
                </div>
                <div className="stack-sm" style={{ marginTop: 14 }}>
                  {(() => {
                    const q = libSearch.trim().toLowerCase();
                    const entries = (Object.values(mediaLibrary) as AnyObj[])
                      .filter((e: AnyObj) => !libEmailOnly || e.email)
                      .filter(
                        (e: AnyObj) =>
                          !q ||
                          [e.name, e.publication, e.role, e.beat, e.article_title, (e.angles ?? []).join(" ")]
                            .join(" ")
                            .toLowerCase()
                            .includes(q)
                      )
                      .sort((a: AnyObj, b: AnyObj) =>
                        String(b.last_seen || "").localeCompare(String(a.last_seen || ""))
                      );
                    if (entries.length === 0) {
                      return (
                        <p className="meta">
                          {Object.keys(mediaLibrary).length === 0
                            ? "No contacts saved yet. Research writers in the Digital PR workflow and they will appear here."
                            : "No saved contacts match this search."}
                        </p>
                      );
                    }
                    return entries.slice(0, 100).map((e: AnyObj, i: number) => (
                      <div className="context-card" key={`${e.name}-${e.publication}-${i}`}>
                        <div className="card-head">
                          <div>
                            <span className="context-value">
                              <strong>{e.name}</strong>{" "}
                              {e.email && <span className="status-pill">Has email</span>}{" "}
                              {draftStatusFor(e.name) && draftStatusFor(e.name) !== "Draft" && (
                                <span className="status-pill active">{draftStatusFor(e.name)}</span>
                              )}
                            </span>
                            <p className="meta">
                              {e.publication}
                              {e.role ? ` · ${e.role}` : ""}
                              {e.beat ? ` · ${e.beat}` : ""}
                            </p>
                          </div>
                          <button
                            className="btn-ghost"
                            onClick={() =>
                              setMediaLibrary((current) => {
                                const next = { ...current };
                                delete next[libraryKey(e.name, e.publication)];
                                return next;
                              })
                            }
                            aria-label={`Delete ${e.name}`}
                            title="Delete this contact"
                          >
                            <X size={15} />
                          </button>
                        </div>
                        {e.email ? (
                          <p className="result-copy">
                            <strong>Email:</strong> {e.email}
                          </p>
                        ) : (
                          <p className="result-meta">No verified email yet — use Find email on their card.</p>
                        )}
                        {e.article_title && (
                          <p className="result-meta">
                            Via: {e.article_title}
                            {e.article_url?.startsWith("https://") && (
                              <>
                                {" · "}
                                <SafeA url={e.article_url}>Open <ExternalLink size={12} className="inline" /></SafeA>
                              </>
                            )}
                          </p>
                        )}
                        <p className="result-meta">
                          Saved {e.first_seen || ""}
                          {e.last_seen && e.last_seen !== e.first_seen ? ` · updated ${e.last_seen}` : ""}
                          {(e.angles ?? []).length > 0 ? ` · ${(e.angles ?? []).slice(-2).join(" · ")}` : ""}
                        </p>
                      </div>
                    ));
                  })()}
                </div>
              </section>

              <section className="card">
                <div className="card-head">
                  <div>
                    <h2 className="section-title">
                      Campaign board · {Object.keys(campaigns).length} saved
                    </h2>
                    <p className="meta">
                      Named snapshots of your workspace. Loading one restores its research and
                      drafts; outcome counts stay live.
                    </p>
                  </div>
                </div>
                <div className="stack-sm" style={{ marginTop: 14 }}>
                  {Object.keys(campaigns).length === 0 ? (
                    <p className="meta">
                      No campaigns yet. Use <strong>Save as campaign</strong> in the Workspace header.
                    </p>
                  ) : (
                    (Object.values(campaigns) as AnyObj[])
                      .sort((a: AnyObj, b: AnyObj) => String(b.created || "").localeCompare(String(a.created || "")))
                      .map((c: AnyObj) => {
                        const keys: string[] = Array.isArray(c.draftKeys) ? c.draftKeys : [];
                        const counts: Record<string, number> = {};
                        const coverage: string[] = [];
                        for (const k of keys) {
                          const st = pitchOutcomes[k]?.status || "Draft";
                          counts[st] = (counts[st] || 0) + 1;
                          if (st === "Covered" && pitchOutcomes[k]?.coverage_url) {
                            coverage.push(pitchOutcomes[k].coverage_url);
                          }
                        }
                        const oppTotal = (Object.values(c.oppByAngle || {}) as AnyObj[]).reduce(
                          (n: number, r: AnyObj) => n + (r?.opportunities?.length || 0),
                          0
                        );
                        const writerTotal = (Object.values(c.writersByOpp || {}) as AnyObj[]).reduce(
                          (n: number, r: AnyObj) => n + (r?.journalists?.length || 0),
                          0
                        );
                        return (
                          <div className="context-card" key={c.id}>
                            <div className="card-head">
                              <div>
                                <span className="context-value">
                                  <strong>{c.name}</strong>
                                </span>
                                <p className="meta">
                                  Saved {c.created || ""} · {oppTotal} opportunities · {writerTotal} writers ·{" "}
                                  {keys.length} drafts
                                  {(counts["Pitched"] || counts["Replied"] || counts["Covered"]) &&
                                    ` · ${counts["Pitched"] || 0} pitched · ${counts["Replied"] || 0} replied · ${counts["Covered"] || 0} covered`}
                                </p>
                              </div>
                              <div className="actions" style={{ marginTop: 0 }}>
                                <button className="btn-secondary" onClick={() => loadCampaign(c.id)}>
                                  Load
                                </button>
                                <button
                                  className="btn-ghost"
                                  onClick={() => {
                                    if (window.confirm(`Delete campaign "${c.name}"?`)) {
                                      setCampaigns((current) => {
                                        const next = { ...current };
                                        delete next[c.id];
                                        return next;
                                      });
                                    }
                                  }}
                                  aria-label={`Delete ${c.name}`}
                                >
                                  <X size={15} />
                                </button>
                              </div>
                            </div>
                            {coverage.length > 0 && (
                              <p className="result-meta">
                                Coverage:{" "}
                                {coverage.map((u, i) => (
                                  <span key={`${u}-${i}`}>
                                    {i > 0 && " · "}
                                    <SafeA url={u}>Link {i + 1} <ExternalLink size={12} className="inline" /></SafeA>
                                  </span>
                                ))}
                              </p>
                            )}
                          </div>
                        );
                      })
                  )}
                </div>
              </section>

              <Note>
                Workspace research resets on reload, but Used marks, the media library, outcomes,
                and campaigns persist in this browser.
                Full saved libraries, backups, and send history live in the local Streamlit app.
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
                  <div className="card-head">
                    <div>
                      <h2 className="section-title">Google Sheet sync</h2>
                      <p className="meta">
                        Pitches, Contacts, Coverage and Dashboard tabs update from this app.
                      </p>
                    </div>
                    <span className={`status-pill ${sheetStatus?.configured ? "active" : ""}`}>
                      {sheetStatus === null
                        ? "Checking..."
                        : sheetStatus?.configured
                          ? "Connected"
                          : "Not connected"}
                    </span>
                  </div>
                  {sheetStatus?.configured && (
                    <div className="setting-row">
                      <span>Mode</span>
                      <strong>{sheetStatus?.mode === "webhook" ? "Apps Script webhook" : "Service account"}</strong>
                    </div>
                  )}
                  <div className="setting-row">
                    <span>Auto-sync after pitches and status changes</span>
                    <strong>{autoSync ? "On" : "Off"}</strong>
                  </div>
                  <div className="actions">
                    <button className="btn-secondary" onClick={testSheetConnection} disabled={checkingSheet}>
                      {checkingSheet ? <Spinner /> : <RefreshCw size={16} />}
                      Test connection
                    </button>
                    <button className="btn-secondary" onClick={copySetupScript}>
                      <Copy size={16} /> Copy setup script
                    </button>
                    <button className="btn-secondary" onClick={() => syncToSheet()} disabled={syncing}>
                      {syncing ? <Spinner /> : <Server size={16} />}
                      Sync now
                    </button>
                  </div>
                  {!sheetStatus?.configured && sheetStatus !== null && (
                    <Note tone="warn">
                      Setup: copy the script, paste it in Extensions → Apps Script, add your token,
                      deploy as a Web app (Anyone), then set SHEET_WEBHOOK_URL and
                      SHEET_WEBHOOK_TOKEN in Vercel.
                    </Note>
                  )}
                  {syncErr && <Note tone="warn">{syncErr}</Note>}
                  {syncMsg && <Note>{syncMsg}</Note>}
                </section>

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
