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

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 1</p>
      <h1 className="page-title">Learning diagnostic</h1>
      <p className="page-copy">
        Answer naturally. XiAv Learn uses your responses to estimate a starting
        level and identify the skills that need the most attention.
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
                id={`answer-${index}`}
                onChange={(event) => {
                  const nextAnswers = [...answers];
                  nextAnswers[index] = event.target.value;
                  setAnswers(nextAnswers);
                }}
                required
                value={answers[index]}
              />
            </Card>
          ))}
          {error ? <div className="error-box">{error}</div> : null}
          <Button disabled={loading} type="submit">
            {loading ? "Evaluating..." : "Submit Diagnostic"}
          </Button>
        </form>
      ) : (
        <section className="mt-8 grid gap-6">
          <Card className="bg-[#14213d] text-white">
            <p className="text-sm font-bold text-[#aebbe8]">Overall level</p>
            <p className="mt-2 text-5xl font-black">{result.overall_level}</p>
            <p className="mt-4 text-[#d6def1]">{result.recommendation}</p>
          </Card>
          <div className="grid md:grid-cols-2 lg:grid-cols-3">
            {Object.entries(result.skill_scores).map(([skill, score]) => (
              <SkillScoreCard key={skill} score={score} skill={skill} />
            ))}
          </div>
          <Card>
            <h2 className="text-xl font-bold">Weak skills</h2>
            <p className="mt-2 text-[#60708a]">{result.weak_skills.join(", ")}</p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button href="/recommendation">See Recommendation</Button>
              <Button href="/dashboard" variant="secondary">
                Go to Dashboard
              </Button>
            </div>
          </Card>
        </section>
      )}
    </main>
  );
}
