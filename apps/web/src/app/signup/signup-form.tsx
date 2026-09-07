"use client";

import Link from "next/link";
import Image from "next/image";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export function SignupForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    if (password.length < 12) {
      setMessage("Use at least 12 characters for your password.");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = (await response.json()) as {
        status?: string;
        message?: string;
        detail?: { message?: string };
      };
      if (!response.ok) throw new Error(body.detail?.message ?? "Account could not be created.");
      if (body.status === "verification_required") {
        setMessage(body.message ?? "Check your email to verify the account.");
        return;
      }
      router.replace("/projects");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Account could not be created.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <Link className="auth-brand" href="/" aria-label="Veyframe home"><Image src="/brand/veyframe-icon.png" width={32} height={32} alt="" /><b>Veyframe</b></Link>
        <p className="auth-kicker">Create your workspace</p>
        <h1>Create your next video with Veyframe</h1>
        <p>Your projects, captures, and exports stay private to your account.</p>
        <form onSubmit={submit}>
          <label htmlFor="signup-email">Email</label>
          <input
            autoComplete="email"
            id="signup-email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <label htmlFor="signup-password">Password</label>
          <input
            autoComplete="new-password"
            id="signup-password"
            minLength={12}
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
          <small>Use at least 12 characters.</small>
          <button className="gradient-button" disabled={loading} type="submit">
            {loading ? "Creating account…" : "Create account"}
          </button>
          {message && <p className="auth-message" role="status">{message}</p>}
        </form>
        <footer>Already have an account? <Link href="/login">Log in</Link></footer>
      </section>
    </main>
  );
}
