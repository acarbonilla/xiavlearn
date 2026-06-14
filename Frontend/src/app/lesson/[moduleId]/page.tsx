"use client";

import { FormEvent, use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  type TeacherSession,
  startTeacherSession,
  submitTeacherFeedback,
} from "@/lib/api";

export default function LessonPage({
  params,
}: {
  params: Promise<{ moduleId: string }>;
}) {
  const { moduleId } = use(params);
  const router = useRouter();
  const numericModuleId = Number(moduleId);
  const hasValidModuleId = Number.isInteger(numericModuleId);
  const [session, setSession] = useState<TeacherSession | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState(
    hasValidModuleId ? "" : "The lesson module ID is invalid.",
  );
  const [loading, setLoading] = useState(hasValidModuleId);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!hasValidModuleId) return;

    startTeacherSession(numericModuleId)
      .then(setSession)
      .catch((requestError: Error) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [hasValidModuleId, numericModuleId]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!session) return;

    setError("");
    setSubmitting(true);
    try {
      const feedback = await submitTeacherFeedback(session.session_id, answer);
      sessionStorage.setItem("xiav-feedback", JSON.stringify(feedback));
      router.push("/feedback");
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 3</p>
      <h1 className="page-title">Guided lesson</h1>
      {loading ? <p className="page-copy">Starting your session...</p> : null}
      {error ? <div className="error-box">{error}</div> : null}

      {session ? (
        <div className="mt-8 grid gap-5">
          <Card>
            <h2 className="text-xl font-bold">Lesson content</h2>
            <p className="mt-3 leading-8 text-[#60708a]">{session.lesson}</p>
          </Card>
          <form onSubmit={handleSubmit}>
            <Card>
              <h2 className="text-xl font-bold">Practice question</h2>
              <p className="mt-3 leading-7">{session.practice_question}</p>
              <label className="field-label mt-6" htmlFor="lesson-answer">
                Your answer
              </label>
              <textarea
                className="text-area"
                id="lesson-answer"
                onChange={(event) => setAnswer(event.target.value)}
                required
                value={answer}
              />
              <Button className="mt-5" disabled={submitting} type="submit">
                {submitting ? "Checking answer..." : "Submit Answer"}
              </Button>
            </Card>
          </form>
        </div>
      ) : null}
    </main>
  );
}
