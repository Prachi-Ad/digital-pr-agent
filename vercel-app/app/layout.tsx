import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Digital PR Agent",
  description: "AI research assistant for Digital PR and listicle prospecting.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}