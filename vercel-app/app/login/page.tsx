"use client";

import { useState } from "react";
import type { FormEvent } from "react";

export default function Login() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
        cache: "no-store",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || "Sign-in failed.");
      const next = new URLSearchParams(window.location.search).get("next") || "/";
      window.location.href = next;
    } catch (err: any) {
      setError(err?.message || "Sign-in failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell" style={{ alignItems: "center", justifyContent: "center" }}>
      <main className="main" style={{ maxWidth: 440 }}>
        <div className="card">
          <div className="page-badge">Vista PR · Private</div>
          <h1 className="page-title" style={{ fontSize: "1.6rem" }}>
            Sign in
          </h1>
          <p className="page-subtitle">
            This demo is private. Enter the shared password to continue.
          </p>
          <form onSubmit={submit} style={{ marginTop: 16 }}>
            <label className="context-label" htmlFor="site-password">
              Password
            </label>
            <input
              id="site-password"
              type="password"
              autoComplete="current-password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Shared password"
              autoFocus
            />
            {error && <div className="note note-warn">{error}</div>}
            <div className="actions">
              <button type="submit" className="btn-primary w-full" disabled={loading || !password}>
                {loading ? "Signing in..." : "Sign in"}
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
