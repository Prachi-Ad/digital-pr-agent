import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

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

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname !== "/") {
    return NextResponse.next();
  }

  const agent = request.headers.get("user-agent") || "";
  const accept = request.headers.get("accept") || "";
  const wantsMarkdown = accept.includes("text/markdown");
  const isAiCrawler = AI_CRAWLERS.some((pattern) => pattern.test(agent));

  if (wantsMarkdown || isAiCrawler) {
    const url = request.nextUrl.clone();
    url.pathname = "/llm";
    return NextResponse.rewrite(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/"],
};
