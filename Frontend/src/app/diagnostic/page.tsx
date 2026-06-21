"use client";

import { useState } from "react";
import type React from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import SkillScoreCard from "@/components/SkillScoreCard";
import {
  type DiagnosticResult,
  submitDiagnostic,
} from "@/lib/api";

const questions = [
  "Introduce yourself in English.",
  "Describe what you did yesterday.",
  "What is your learning goal?",
];

export default function DiagnosticPage() {
  const [answers, setAnswers] = useState(["", "", ""]);
  const [result, setResult] = useState<DiagnosticResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await submitDiagnostic(
        questions.map((question, index) => ({
          question,
          answer: answers[index],
        })),
      );
      setResult(data);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function updateAnswer(index: number, value: string) {
    const nextAnswers = [...answers];
    nextAnswers[index] = value;
    setAnswers(nextAnswers);
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 1</p>
      <h1 className="page-title">Learning diagnostic</h1>
      <p className="page-copy">
        Answer naturally. XiAv Learn evaluates your responses, explains the
        assigned level, and shows what to improve before you continue.
      </p>

      {!result ? (
        <form className="mt-8 grid gap-4" onSubmit={handleSubmit}>
          {questions.map((question, index) => (
            <Card key={question}>
              <label className="field-label" htmlFor={`answer-${index}`}>
                {index + 1}. {question}
              </label>
              <textarea
                className="text-area"
                disabled={loading}
                id={`answer-${index}`}
                onChange={(event) => updateAnswer(index, event.target.value)}
                required
                value={answers[index]}
              />
            </Card>
          ))}
          {error ? <div className="error-box">{error}</div> : null}
          <Button disabled={loading} type="submit">
            {loading ? "Evaluating diagnostic..." : "Submit Diagnostic"}
          </Button>
        </form>
      ) : (
        <section className="mt-8 grid gap-6">
          <Card>
            <div
              className="-m-6 rounded-2xl p-6 text-white"
              style={{ backgroundColor: "#14213d" }}
            >
              <p className="text-sm font-bold uppercase tracking-[0.16em]" style={{ color: "#aebbe8" }}>
                Text-only assessment
              </p>
              <p className="mt-3 text-sm font-bold" style={{ color: "#d6def1" }}>
                Assigned level
              </p>
              <p className="mt-2 text-5xl font-black text-white">{result.overall_level}</p>
              <p className="mt-4 text-lg font-semibold text-white">
                {result.recommendation}
              </p>
              <p className="mt-4" style={{ color: "#d6def1" }}>
                {result.level_explanation}
              </p>
            </div>
          </Card>

          <section className="grid gap-4">
            <div>
              <h2 className="text-xl font-bold text-[#14213d]">Assessed skills</h2>
              <p className="mt-1 text-sm text-[#60708a]">
                This diagnostic scores grammar and vocabulary from written answers only.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {result.assessed_skills.map((skill) => {
                const score = result.skill_scores[skill];
                return typeof score === "number" ? (
                  <SkillScoreCard
                    key={skill}
                    diagnosticType="Text Diagnostic"
                    score={score}
                    skill={skill}
                  />
                ) : null;
              })}
            </div>
          </section>

          <section className="grid gap-4">
            <div>
              <h2 className="text-xl font-bold text-[#14213d]">Skills not assessed yet</h2>
              <p className="mt-1 text-sm text-[#60708a]">
                Speaking, listening, and pronunciation need voice or audio-based checks.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              {result.unassessed_skills.map((skill) => (
                <Card key={skill}>
                  <p className="text-lg font-bold text-[#14213d]">{skill}</p>
                  <p className="mt-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#335cff]">
                    {result.skill_status[skill]}
                  </p>
                </Card>
              ))}
            </div>
          </section>

          <Card>
            <h2 className="text-xl font-bold text-[#14213d]">What to focus on next</h2>
            <p className="mt-2 text-[#60708a]">
              Weak assessed skills: {result.weak_skills.join(", ")}
            </p>
            <p className="mt-4 text-[#42536b]">{result.next_step}</p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button href="/dashboard">Continue to Dashboard</Button>
              <Button href="/recommendation" variant="secondary">
                View Recommended Lesson
              </Button>
            </div>
          </Card>

          <Card>
            <h2 className="text-xl font-bold text-[#14213d]">
              How the agent evaluated your answers
            </h2>
            <div className="mt-5 grid gap-4">
              {result.answer_feedback.map((item, index) => (
                <section
                  className="rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-5"
                  key={`${item.question}-${index}`}
                >
                  <p className="text-sm font-bold uppercase tracking-[0.16em] text-[#335cff]">
                    Question {index + 1}
                  </p>
                  <p className="mt-2 font-bold text-[#14213d]">{item.question}</p>
                  <p className="mt-3 text-sm text-[#60708a]">Your answer</p>
                  <p className="mt-1 text-[#14213d]">{item.answer}</p>
                  <p className="mt-4 text-sm text-[#60708a]">Agent feedback</p>
                  <p className="mt-1 text-[#14213d]">{item.feedback}</p>
                  <p className="mt-4 text-sm text-[#60708a]">Suggested correction</p>
                  <p className="mt-1 text-[#14213d]">{item.corrected_answer}</p>
                  {item.mistakes.length ? (
                    <div className="mt-4 grid gap-3">
                      {item.mistakes.map((mistake, mistakeIndex) => (
                        <div
                          className="rounded-2xl border border-[#dce4ef] bg-white p-4"
                          key={`${mistake.type}-${mistakeIndex}`}
                        >
                          <p className="text-sm font-bold text-[#14213d]">{mistake.type}</p>
                          <p className="mt-2 text-sm text-[#60708a]">
                            <span className="font-semibold text-[#42536b]">Original:</span>{" "}
                            {mistake.original}
                          </p>
                          <p className="mt-1 text-sm text-[#60708a]">
                            <span className="font-semibold text-[#42536b]">Correction:</span>{" "}
                            {mistake.correction}
                          </p>
                          <p className="mt-2 text-sm text-[#42536b]">{mistake.explanation}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </section>
              ))}
            </div>
          </Card>
        </section>
      )}
    </main>
  );
}
