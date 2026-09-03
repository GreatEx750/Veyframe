"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [judgeLoading, setJudgeLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setLoading(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, return_to: "/projects" }),
      });
      const body = (await response.json()) as {
        detail?: { message?: string };
      };
      if (!response.ok) throw new Error(body.detail?.message ?? "Email or password is incorrect.");
      router.replace("/projects");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Email or password is incorrect.");
    } finally {
      setLoading(false);
    }
  }

  async function enterJudgeDemo() {
    setMessage(null);
    setJudgeLoading(true);
    try {
      const response = await fetch("/api/auth/judge-session", { method: "POST" });
      const body = (await response.json()) as {
        detail?: { message?: string };
      };
      if (!response.ok) throw new Error(body.detail?.message ?? "Judge demo is unavailable.");
      router.replace("/projects");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Judge demo is unavailable.");
    } finally {
      setJudgeLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="auth-brand"><span>◆</span><b>DemoDirector</b></div>
        <p className="auth-kicker">Welcome back</p>
        <h1>Continue creating your demo</h1>
        <p>Log in to open your private projects, media, and exports.</p>
        <form onSubmit={submit}>
          <label htmlFor="login-email">Email</label>
          <input autoComplete="email" id="login-email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          <label htmlFor="login-password">Password</label>
          <input autoComplete="current-password" id="login-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
          <button className="gradient-button" disabled={loading} type="submit">{loading ? "Logging in…" : "Log in"}</button>
          {message && <p className="auth-message" role="alert">{message}</p>}
        </form>
        <div className="auth-divider"><span>or evaluate instantly</span></div>
        <button className="judge-entry" disabled={judgeLoading} onClick={enterJudgeDemo} type="button">
          {judgeLoading ? "Preparing judge demo…" : "Enter Judge Demo"}
        </button>
        <small className="judge-note">Short-lived, isolated, and preloaded. No shared password.</small>
        <footer>New to DemoDirector? <Link href="/signup">Create an account</Link></footer>
      </section>
    </main>
  );
}
