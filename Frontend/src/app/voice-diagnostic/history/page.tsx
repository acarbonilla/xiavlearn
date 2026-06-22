"use client";

import { useEffect, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  getVoiceDiagnosticSessions,
  type VoiceDiagnosticHistorySession,
} from "@/lib/api";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatScore(value: number | null) {
  return value === null ? "Pending" : `${value}%`;
}

export default function VoiceDiagnosticHistoryPage() {
  const [sessions, setSessions] = useState<VoiceDiagnosticHistorySession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    getVoiceDiagnosticSessions()
      .then((data) => {
        if (active) {
          setSessions(data);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load voice diagnostic history.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="page-shell">
      <p className="eyebrow">Official voice assessment history</p>
      <h1 className="page-title">Voice Diagnostic History</h1>
      <p className="page-copy">
        Review saved official attempts, compare the three voice scores, and open item-level results.
      </p>

      {error ? <div className="error-box">{error}</div> : null}

      <div className="mt-8 flex flex-wrap gap-3">
        <Button href="/voice-diagnostic">Back to Voice Diagnostic</Button>
        <Button href="/dashboard" variant="secondary">
          Return to Dashboard
        </Button>
      </div>

      {loading ? (
        <Card className="mt-8">
          <p className="text-[#42536b]">Loading saved voice diagnostic sessions...</p>
        </Card>
      ) : null}

      {!loading && !sessions.length ? (
        <Card className="mt-8">
          <p className="eyebrow">No history yet</p>
          <h2 className="mt-2 text-2xl font-black text-[#14213d]">Your first saved attempt will appear here</h2>
          <p className="mt-3 text-[#60708a]">
            Start the official voice diagnostic to store a full session with pronunciation, listening, and speaking
            item results.
          </p>
        </Card>
      ) : null}

      {!loading ? (
        <section className="mt-8 grid gap-4">
          {sessions.map((session) => (
            <Card key={session.id}>
              <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="eyebrow">Attempt {session.id}</p>
                  <h2 className="mt-2 text-2xl font-black text-[#14213d]">{formatDate(session.started_at)}</h2>
                  <p className="mt-3 text-[#60708a]">
                    Status: {session.status.replaceAll("_", " ")}
                    {session.completed_at ? ` | Completed ${formatDate(session.completed_at)}` : ""}
                  </p>
                  <p className="mt-4 text-[#42536b]">
                    {session.summary || "This attempt is still in progress."}
                  </p>
                </div>

                <div className="grid min-w-[280px] gap-3">
                  <div className="rounded-2xl border border-[#dce4ef] bg-[#f8fafc] px-4 py-3 text-[#14213d]">
                    Pronunciation: {formatScore(session.pronunciation_score)}
                  </div>
                  <div className="rounded-2xl border border-[#dce4ef] bg-[#f8fafc] px-4 py-3 text-[#14213d]">
                    Listening: {formatScore(session.listening_score)}
                  </div>
                  <div className="rounded-2xl border border-[#dce4ef] bg-[#f8fafc] px-4 py-3 text-[#14213d]">
                    Speaking: {formatScore(session.speaking_score)}
                  </div>
                  <div className="rounded-2xl border border-[#e6ebf2] bg-white px-4 py-3 text-sm text-[#60708a]">
                    Recommended focus: {session.recommended_focus || "Pending"}
                  </div>
                  <div className="flex gap-3">
                    <Button href={`/voice-diagnostic/history/${session.id}`}>View Details</Button>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </section>
      ) : null}
    </main>
  );
}
