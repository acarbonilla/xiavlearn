"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  type GuidedTeacherSession,
  getGuidedTeacherSession,
  startGuidedTeacherSession,
  submitGuidedTeacherAnswer,
} from "@/lib/api";

function FeedbackPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const moduleIdParam = searchParams.get("moduleId");
  const sessionIdParam = searchParams.get("sessionId");

  const [session, setSession] = useState<GuidedTeacherSession | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadSession() {
      setError("");
      setLoading(true);

      try {
        if (sessionIdParam) {
          const numericSessionId = Number(sessionIdParam);
          if (!Number.isInteger(numericSessionId)) {
            throw new Error("The teacher session ID is invalid.");
          }
          const existingSession = await getGuidedTeacherSession(numericSessionId);
          if (!cancelled) {
            setSession(existingSession);
          }
          return;
        }

        if (moduleIdParam) {
          const numericModuleId = Number(moduleIdParam);
          if (!Number.isInteger(numericModuleId)) {
            throw new Error("The lesson module ID is invalid.");
          }
          const newSession = await startGuidedTeacherSession(numericModuleId);
          if (!cancelled) {
            setSession(newSession);
            router.replace(`/feedback?sessionId=${newSession.session_id}`);
          }
          return;
        }

        if (!cancelled) {
          setSession(null);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError((requestError as Error).message);
          setSession(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSession();

    return () => {
      cancelled = true;
    };
  }, [moduleIdParam, router, sessionIdParam]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!session?.current_task) {
      return;
    }

    setError("");
    setSubmitting(true);
    try {
      await submitGuidedTeacherAnswer(session.session_id, answer);
      const refreshedSession = await getGuidedTeacherSession(session.session_id);
      setSession(refreshedSession);
      setAnswer("");
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 4</p>
      <h1 className="page-title">AI Teacher Session</h1>
      <p className="page-copy">
        Complete three guided tasks, review each correction, and finish with a
        final session score before generating your study plan.
      </p>

      {loading ? <p className="mt-8 text-[#60708a]">Starting your session...</p> : null}
      {error ? <div className="error-box">{error}</div> : null}

      {!loading && !session && !error ? (
        <Card className="mt-8 max-w-2xl">
          <h2 className="text-xl font-bold">No teacher session yet</h2>
          <p className="mt-3 text-[#60708a]">
            Start from your recommendation to begin a guided lesson session.
          </p>
          <Button className="mt-5" href="/recommendation">
            Back to Recommendation
          </Button>
        </Card>
      ) : null}

      {session ? (
        <div className="mt-8 grid gap-5">
          <Card>
            <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
              {session.module?.level} Lesson {"\u2022"} {session.module?.skill} Focus
            </p>
            <h2 className="mt-3 text-2xl font-black">
              {session.module?.title ?? "Guided lesson"}
            </h2>
            <p className="mt-4 leading-7 text-[#60708a]">{session.lesson}</p>
          </Card>

          {session.status !== "completed" ? (
            <form onSubmit={handleSubmit}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-xl font-bold">Current task</h2>
                  <span className="rounded-full bg-[#e9eeff] px-3 py-1 text-sm font-bold text-[#335cff]">
                    Task {session.current_turn} of {session.total_turns}
                  </span>
                </div>
                <p className="mt-4 text-sm font-bold uppercase tracking-wider text-[#60708a]">
                  Lesson objective
                </p>
                <p className="mt-2 leading-7 text-[#42536b]">
                  {session.lesson_objective}
                </p>
                <p className="mt-6 text-sm font-bold uppercase tracking-wider text-[#60708a]">
                  Task
                </p>
                <p className="mt-4 leading-7 text-[#14213d]">
                  {session.current_task?.teacher_task}
                </p>
                <label className="field-label mt-6" htmlFor="teacher-answer">
                  Your answer
                </label>
                <textarea
                  className="text-area"
                  id="teacher-answer"
                  onChange={(event) => setAnswer(event.target.value)}
                  required
                  value={answer}
                />
                <Button className="mt-5" disabled={submitting} type="submit">
                  {submitting ? "Checking answer..." : "Submit answer"}
                </Button>
              </Card>
            </form>
          ) : null}

          {session.turns.length ? (
            <section className="grid gap-4">
              <h2 className="text-xl font-bold text-[#14213d]">Previous feedback</h2>
              {session.turns.map((turn) => (
                <Card key={turn.turn_number}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="text-lg font-bold">Task {turn.turn_number}</h3>
                    <span className="rounded-full bg-[#14213d] px-3 py-1 text-sm font-bold text-white">
                      {turn.score ?? "Not scored"}%
                    </span>
                  </div>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Teacher task</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.teacher_task}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Your answer</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.student_answer}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Feedback</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.feedback}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Correction</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.correction}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Explanation</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.explanation}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Encouragement</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.encouragement}</p>
                </Card>
              ))}
            </section>
          ) : null}

          {session.final_result ? (
            <div className="grid gap-5 md:grid-cols-2">
              <Card className="bg-[#f4f7ff]">
                <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                  Session Score
                </p>
                <div className="mt-4 inline-flex rounded-2xl bg-[#335cff] px-5 py-4 text-white shadow-[0_12px_24px_rgba(51,92,255,0.22)]">
                  <p className="text-6xl font-black">
                    {session.final_result.session_score}%
                  </p>
                </div>
                <p className="mt-6 leading-7 text-[#14213d]">
                  {session.final_result.feedback_summary}
                </p>
                <p className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm leading-6 text-[#42536b]">
                  This score reflects this practice session. Official mastery
                  updates after diagnostics.
                </p>
                <p className="mt-6 text-sm font-bold uppercase tracking-wider text-[#335cff]">
                  Next study suggestion
                </p>
                <p className="mt-2 leading-7 text-[#42536b]">
                  {session.final_result.next_study_suggestion}
                </p>
              </Card>
              <div className="grid gap-5">
                <Card>
                  <h3 className="text-lg font-bold">Strengths</h3>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-[#42536b]">
                    {session.final_result.strengths.map((strength) => (
                      <li key={strength}>{strength}</li>
                    ))}
                  </ul>
                  <h3 className="mt-6 text-lg font-bold">Improvement areas</h3>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-[#42536b]">
                    {session.final_result.improvement_areas.map((area) => (
                      <li key={area}>{area}</li>
                    ))}
                  </ul>
                </Card>
                <Button href="/study-plan">Generate Study Plan</Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}

export default function FeedbackPage() {
  return (
    <Suspense
      fallback={
        <main className="page-shell">
          <p className="eyebrow">Step 4</p>
          <h1 className="page-title">AI Teacher Session</h1>
          <p className="mt-8 text-[#60708a]">Starting your session...</p>
        </main>
      }
    >
      <FeedbackPageContent />
    </Suspense>
  );
}
