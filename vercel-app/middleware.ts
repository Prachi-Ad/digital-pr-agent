import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_COOKIE = "pr_auth";
const AUTH_MESSAGE = "vista-pr-auth-v1";

const AI_CRAWLERS = [
  /GPTBot/i,
  /OAI-SearchBot/i,
  /ChatGPT-User/i,
  /ClaudeBot/i,
  /Claude-Web/i,
  /anthropic-ai/i,
  /PerplexityBot/i,
  /Google-Extended/i,
  /Applebot-Extended/i,
  /CCBot/i,
  /cohere-ai/i,
  /YouBot/i,
];

function base64url(bytes: ArrayBuffer): string {
  const arr = new Uint8Array(bytes);
  let binary = "";
  for (let i = 0; i < arr.length; i += 1) binary += String.fromCharCode(arr[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function expectedAuthValue(password: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(AUTH_MESSAGE));
  return base64url(sig);
}

function safeEqual(a: string, b: string): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function isAuthenticated(request: NextRequest): Promise<boolean> {
  const password = (process.env.SITE_PASSWORD || "").trim();
  if (!password) return false;
  const provided = request.cookies.get(AUTH_COOKIE)?.value?.trim() || "";
  if (!provided) return false;
  try {
    return safeEqual(provided, await expectedAuthValue(password));
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Public machine-readable endpoints stay open for AI crawlers and everyone.
  if (
    pathname === "/llm" ||
    pathname === "/llms.txt" ||
    pathname === "/robots.txt" ||
    pathname === "/favicon.ico" ||
    pathname.startsWith("/skills/") ||
    pathname.startsWith("/_next/")
  ) {
    return NextResponse.next();
  }

  // Login + login API are public (the login API fails closed without SITE_PASSWORD).
  if (pathname === "/login" || pathname === "/api/login") {
    return NextResponse.next();
  }

  // AI crawlers and Markdown clients keep reading the Markdown summary at /
  // without needing the shared password. Browsers still sign in.
  if (pathname === "/") {
    const agent = request.headers.get("user-agent") || "";
    const accept = request.headers.get("accept") || "";
    const wantsMarkdown = accept.includes("text/markdown");
    const isAiCrawler = AI_CRAWLERS.some((pattern) => pattern.test(agent));
    if (wantsMarkdown || isAiCrawler) {
      const url = request.nextUrl.clone();
      url.pathname = "/llm";
      return NextResponse.rewrite(url);
    }
    if (await isAuthenticated(request)) return NextResponse.next();
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", "/");
    return NextResponse.redirect(url);
  }

  // Token minting requires the same gate; the Python /api/analyze guard
  // re-checks the cookie since that function does not run through Next.
  if (pathname === "/api/token") {
    if (await isAuthenticated(request)) return NextResponse.next();
    return NextResponse.json(
      { detail: "Sign in required." },
      { status: 401, headers: { "Cache-Control": "no-store" } }
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/api/token"],
};
