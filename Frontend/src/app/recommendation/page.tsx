"use client";

import { useEffect, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  type RecommendationData,
  getRecommendation,
} from "@/lib/api";

const scoreRows = [
  "Grammar",
  "Vocabulary",
  "Listening",
  "Speaking",
  "Pronunciation",
] as const;

function buildRecommendationCopy(recommendation: RecommendationData) {
  const focusSkill = recommendation.recommended_focus ?? recommendation.weakest_skill;
  if (!focusSkill) {
    return {
      summary: recommendation.reason,
      detail: recommendation.reason,
      focusLabel: "Not available",
    };
  }

  return {
    summary: recommendation.reason,
    detail: recommendation.recommended_focus_reason || recommendation.reason,
    focusLabel: focusSkill,
  };
}

export default function RecommendationPage() {
  const [recommendation, setRecommendation] =
    useState<RecommendationData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getRecommendation()
      .then(setRecommendation)
      .catch((requestError: Error) => setError(requestError.message));
  }, []);

  const recommendationCopy = recommendation
    ? buildRecommendationCopy(recommendation)
    : null;
  const recommendedAction = recommendation?.recommended_action ?? null;
  const isVoiceRecommendation =
    recommendedAction?.type === "teacher_session";

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 2</p>
      <h1 className="page-title">Your recommendation</h1>

      {!recommendation && !error ? (
        <p className="page-copy">Finding your next best official focus...</p>
      ) : null}
      {error ? <div className="error-box">{error}</div> : null}

      {recommendation ? (
        <Card className="mt-8 max-w-3xl">
          {recommendation.recommended_module ? (
            <>
              <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                {recommendation.fallback_used
                  ? `${recommendation.recommended_module.level} Review - ${recommendation.recommended_module.skill}`
                  : `${recommendation.learner_level} - ${recommendation.recommended_module.skill}`}
              </p>
              {recommendation.fallback_used ? (
                <div className="mt-4 rounded-2xl border border-[#facc15] bg-[#fffbeb] px-4 py-3 text-sm leading-6 text-[#7c5e10]">
                  {`No ${recommendation.learner_level} module is available yet. Showing ${recommendation.module_level} review lesson.`}
                  {recommendation.fallback_reason ? (
                    <span className="mt-1 block">{recommendation.fallback_reason}</span>
                  ) : null}
                </div>
              ) : null}
              <h2 className="mt-3 text-3xl font-black">
                {recommendation.recommended_module.title}
              </h2>
              <p className="mt-4 leading-7 text-[#60708a]">
                {recommendationCopy?.summary}
              </p>
            </>
          ) : isVoiceRecommendation ? (
            <>
              <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                Official Voice Focus
              </p>
              <h2 className="mt-3 text-3xl font-black">
                {recommendationCopy?.focusLabel} Teacher Session
              </h2>
              <p className="mt-4 leading-7 text-[#60708a]">
                {recommendationCopy?.summary}
              </p>
            </>
          ) : (
            <>
              <h2 className="text-2xl font-bold">No active module found</h2>
              <p className="mt-3 text-[#60708a]">{recommendation.reason}</p>
            </>
          )}

          <section className="mt-6 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-5">
            <h3 className="text-lg font-black text-[#14213d]">
              Your Current Official Skill Scores
            </h3>
            <p className="mt-2 leading-7 text-[#60708a]">
              These scores reflect your latest official mastery. Voice teacher
              sessions are practice-only and do not change these scores.
            </p>
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
                    {recommendation.current_skill_scores[skill] ??
                      "Not assessed"}
                  </span>
                </div>
              ))}
              <div className="flex items-center justify-between gap-4 pt-1">
                <span className="font-semibold text-[#42536b]">
                  Recommended Focus
                </span>
                <span className="font-black text-[#14213d]">
                  {recommendationCopy?.focusLabel ?? "Not available"}
                </span>
              </div>
            </div>
          </section>

          <section className="mt-6">
            <h3 className="text-lg font-black text-[#14213d]">
              Why this focus?
            </h3>
            <p className="mt-2 leading-7 text-[#60708a]">
              {recommendationCopy?.detail}
            </p>
          </section>

          {recommendedAction ? (
            <Button className="mt-6" href={recommendedAction.href}>
              {recommendedAction.label}
            </Button>
          ) : null}
        </Card>
      ) : null}
    </main>
  );
}
