"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type React from "react";

import Card from "@/components/Card";
import { registerUser } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await registerUser(username, email, password);
      router.push("/diagnostic");
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="mx-auto max-w-2xl">
        <p className="eyebrow">Start your journey</p>
        <h1 className="page-title">Create your XiAv Learn account</h1>
        <Card className="mt-8">
          <form className="grid gap-4" onSubmit={handleSubmit}>
            <div>
              <label className="field-label" htmlFor="username">
                Username
              </label>
              <input
                autoComplete="username"
                className="text-input"
                id="username"
                onChange={(event) => setUsername(event.target.value)}
                required
                value={username}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="email">
                Email
              </label>
              <input
                autoComplete="email"
                className="text-input"
                id="email"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="password">
                Password
              </label>
              <input
                autoComplete="new-password"
                className="text-input"
                id="password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="confirm-password">
                Confirm password
              </label>
              <input
                autoComplete="new-password"
                className="text-input"
                id="confirm-password"
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
                type="password"
                value={confirmPassword}
              />
            </div>
            {error ? <div className="error-box">{error}</div> : null}
            <button
              className="rounded-xl bg-[#335cff] px-5 py-3 font-bold text-white transition hover:bg-[#2447d8] disabled:opacity-60"
              disabled={loading}
              type="submit"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>
          <p className="mt-5 text-[#60708a]">
            Already registered?{" "}
            <Link className="font-bold text-[#335cff]" href="/login">
              Log in
            </Link>
          </p>
        </Card>
      </div>
    </main>
  );
}
