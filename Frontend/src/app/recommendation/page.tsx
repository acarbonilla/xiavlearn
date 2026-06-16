"use client";

import { useEffect, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  type RecommendationData,
  getRecommendation,
} from "@/lib/api";

const scoreRows = [
  "Vocabulary",
  "Grammar",
  "Listening",
  "Speaking",
] as const;

export default function RecommendationPage() {
  const [recommendation, setRecommendation] =
    useState<RecommendationData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getRecommendation()
      .then(setRecommendation)
      .catch((requestError: Error) => setError(requestError.message));
  }, []);

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 2</p>
      <h1 className="page-title">Your recommendation</h1>

      {!recommendation && !error ? (
        <p className="page-copy">Finding your next best module...</p>
      ) : null}
      {error ? <div className="error-box">{error}</div> : null}

      {recommendation ? (
        <Card className="mt-8 max-w-3xl">
          {recommendation.recommended_module ? (
            <>
              <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                {recommendation.recommended_module.level} ·{" "}
                {recommendation.recommended_module.skill}
              </p>
              <h2 className="mt-3 text-3xl font-black">
                {recommendation.recommended_module.title}
              </h2>
              <p className="mt-4 leading-7 text-[#60708a]">
                {recommendation.reason}
              </p>
              <section className="mt-6 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-5">
                <h3 className="text-lg font-black text-[#14213d]">
                  Your Assessment Results
                </h3>
                <div className="mt-4 grid gap-3">
                  {scoreRows.map((skill) => (
                    <div
                      className="flex items-center justify-between gap-4 border-b border-[#dce4ef] pb-3 last:border-b-0 last:pb-0"
                      key={skill}
                    >
                      <span className="font-semibold text-[#42536b]">
                        {skill} Score
                      </span>
                      <span className="font-black text-[#14213d]">
                        {recommendation.diagnostic_scores[skill] ?? "Not assessed"}
                      </span>
                    </div>
                  ))}
                  <div className="flex items-center justify-between gap-4 pt-1">
                    <span className="font-semibold text-[#42536b]">
                      Weakest Skill
                    </span>
                    <span className="font-black text-[#14213d]">
                      {recommendation.weakest_skill ?? "Not available"}
                    </span>
                  </div>
                </div>
              </section>
              <section className="mt-6">
                <h3 className="text-lg font-black text-[#14213d]">
                  Why this lesson?
                </h3>
                <p className="mt-2 leading-7 text-[#60708a]">
                  {recommendation.reason}
                </p>
              </section>
              <Button
                className="mt-6"
                href={`/lesson/${recommendation.recommended_module.id}`}
              >
                Start Lesson
              </Button>
            </>
          ) : (
            <>
              <h2 className="text-2xl font-bold">No active module found</h2>
              <p className="mt-3 text-[#60708a]">{recommendation.reason}</p>
            </>
          )}
        </Card>
      ) : null}
    </main>
  );
}
