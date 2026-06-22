"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  getVoiceDiagnosticSession,
  type VoiceDiagnosticHistoryDetail,
  type VoiceDiagnosticHistoryItem,
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

function readStringArray(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function readNumber(value: unknown) {
  return typeof value === "number" ? value : null;
}

function hasRubricDetails(details: Record<string, unknown>) {
  return typeof details.rubric === "string";
}

function renderItemDetails(item: VoiceDiagnosticHistoryItem) {
  if (!hasRubricDetails(item.details)) {
    return (
      <p className="mt-3 text-sm text-[#60708a]">
        Detailed rubric breakdown is not available for this attempt.
      </p>
    );
  }

  if (item.skill === "Pronunciation") {
    const missingWords = readStringArray(item.details.missing_words);
    const extraWords = readStringArray(item.details.extra_words);
    return (
      <>
        <p className="mt-3 text-sm text-[#60708a]">
          Word accuracy: {String(readNumber(item.details.word_accuracy) ?? "N/A")}%
        </p>
        <p className="mt-2 text-sm text-[#60708a]">
          Target completion: {String(readNumber(item.details.target_completion) ?? "N/A")}%
        </p>
        <p className="mt-2 text-sm text-[#60708a]">
          Missing words: {missingWords.length ? missingWords.join(", ") : "None"}
        </p>
        <p className="mt-2 text-sm text-[#60708a]">
          Extra words: {extraWords.length ? extraWords.join(", ") : "None"}
        </p>
      </>
    );
  }

  if (item.skill === "Listening") {
    const matchedKeywords = readStringArray(item.details.matched_keywords);
    const missingKeywords = readStringArray(item.details.missing_keywords);
    return (
      <>
        <p className="mt-3 text-sm text-[#60708a]">
          Correct detail: {String(readNumber(item.details.correct_detail) ?? "N/A")}%
        </p>
        <p className="mt-2 text-sm text-[#60708a]">
          Matched keywords: {matchedKeywords.length ? matchedKeywords.join(", ") : "None"}
        </p>
        <p className="mt-2 text-sm text-[#60708a]">
          Missing keywords: {missingKeywords.length ? missingKeywords.join(", ") : "None"}
        </p>
        <p className="mt-2 text-sm text-[#60708a]">
          Answer match: {String(item.details.answer_match ?? "unknown")}
        </p>
      </>
    );
  }

  const strengths = readStringArray(item.details.strengths);
  const improvementAreas = readStringArray(item.details.improvement_areas);
  return (
    <>
      <p className="mt-3 text-sm text-[#60708a]">
        Task relevance: {String(readNumber(item.details.task_relevance) ?? "N/A")}%
      </p>
      <p className="mt-2 text-sm text-[#60708a]">
        Completeness: {String(readNumber(item.details.completeness) ?? "N/A")}%
      </p>
      <p className="mt-2 text-sm text-[#60708a]">
        Grammar control: {String(readNumber(item.details.grammar_control) ?? "N/A")}%
      </p>
      <p className="mt-2 text-sm text-[#60708a]">Strengths: {strengths.length ? strengths.join(", ") : "None"}</p>
      <p className="mt-2 text-sm text-[#60708a]">
        Improvement areas: {improvementAreas.length ? improvementAreas.join(", ") : "None"}
      </p>
    </>
  );
}

export default function VoiceDiagnosticHistoryDetailPage() {
  const params = useParams<{ id: string }>();
  const sessionId = Number(params.id);
  const invalidSessionId = !Number.isFinite(sessionId);
  const [session, setSession] = useState<VoiceDiagnosticHistoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (invalidSessionId) {
      return;
    }

    let active = true;

    getVoiceDiagnosticSession(sessionId)
      .then((data) => {
        if (active) {
          setSession(data);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load this voice diagnostic session.");
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
  }, [invalidSessionId, sessionId]);

  return (
    <main className="page-shell">
      <p className="eyebrow">Saved official attempt</p>
      <h1 className="page-title">Voice Diagnostic Session</h1>
      <p className="page-copy">Review the final scores and the item-level evidence saved for this attempt.</p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Button href="/voice-diagnostic/history">Back to History</Button>
        <Button href="/voice-diagnostic" variant="secondary">
          Start New Diagnostic
        </Button>
      </div>

      {invalidSessionId ? <div className="error-box mt-8">Invalid voice diagnostic session.</div> : null}
      {error ? <div className="error-box mt-8">{error}</div> : null}

      {loading && !invalidSessionId ? (
        <Card className="mt-8">
          <p className="text-[#42536b]">Loading voice diagnostic details...</p>
        </Card>
      ) : null}

      {session && !invalidSessionId ? (
        <>
          <Card className="mt-8">
            <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
              <div>
                <p className="eyebrow">Attempt {session.id}</p>
                <h2 className="mt-2 text-3xl font-black text-[#14213d]">{formatDate(session.started_at)}</h2>
                <p className="mt-3 text-[#60708a]">
                  Status: {session.status.replaceAll("_", " ")}
                  {session.completed_at ? ` | Completed ${formatDate(session.completed_at)}` : ""}
                </p>
                <p className="mt-4 text-[#42536b]">{session.summary || "This attempt is still in progress."}</p>
              </div>

              <div className="grid gap-3">
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
              </div>
            </div>
          </Card>

          <section className="mt-8 grid gap-4">
            {session.items.map((item) => (
              <Card key={item.id}>
                <p className="eyebrow">
                  {item.skill} Item {item.item_number}
                </p>
                <h2 className="mt-2 text-2xl font-black text-[#14213d]">{formatScore(item.score)}</h2>
                <p className="mt-3 text-[#42536b]">{item.feedback || "No feedback saved."}</p>

                {item.target_text ? (
                  <p className="mt-4 text-sm text-[#60708a]">Target: {item.target_text}</p>
                ) : null}
                {item.passage_text ? (
                  <p className="mt-4 text-sm text-[#60708a]">Passage: {item.passage_text}</p>
                ) : null}
                {item.question_text ? (
                  <p className="mt-4 text-sm text-[#60708a]">Question: {item.question_text}</p>
                ) : null}
                {item.expected_answer ? (
                  <p className="mt-2 text-sm text-[#60708a]">Expected answer: {item.expected_answer}</p>
                ) : null}
                {item.user_answer ? (
                  <p className="mt-2 text-sm text-[#60708a]">User answer: {item.user_answer}</p>
                ) : null}
                {item.transcript ? (
                  <p className="mt-2 text-sm text-[#60708a]">Transcript: {item.transcript}</p>
                ) : null}

                {renderItemDetails(item)}
              </Card>
            ))}
          </section>
        </>
      ) : null}
    </main>
  );
}
