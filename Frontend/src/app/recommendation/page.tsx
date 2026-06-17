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

function buildRecommendationCopy(recommendation: RecommendationData) {
  const focusSkill = recommendation.weakest_skill;
  if (!focusSkill) {
    return {
      summary: recommendation.reason,
      detail: recommendation.reason,
      focusLabel: "Not available",
    };
  }

  const scoreLookup = recommendation.current_skill_scores as Record<
    string,
    number | null
  >;
  const focusScore = scoreLookup[focusSkill];

  if (typeof focusScore !== "number") {
    return {
      summary: recommendation.reason,
      detail: recommendation.reason,
      focusLabel: focusSkill,
    };
  }

  if (focusScore < 80) {
    return {
      summary: `${focusSkill} is your weakest skill.`,
      detail: `${focusSkill} is your lowest current skill score, so this lesson helps strengthen that area.`,
      focusLabel: focusSkill,
    };
  }

  return {
    summary: `${focusSkill} is your recommended focus area.`,
    detail: `Your skills are performing well. ${focusSkill} is selected as your recommended focus area for continued improvement.`,
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
                {recommendation.recommended_module.level} Lesson {"\u2022"}{" "}
                {recommendation.recommended_module.skill} Focus
              </p>
              <h2 className="mt-3 text-3xl font-black">
                {recommendation.recommended_module.title}
              </h2>
              <p className="mt-4 leading-7 text-[#60708a]">
                {recommendationCopy?.summary}
              </p>
              <section className="mt-6 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-5">
                <h3 className="text-lg font-black text-[#14213d]">
                  Your Current Skill Scores
                </h3>
                <p className="mt-2 leading-7 text-[#60708a]">
                  These scores reflect your latest skill mastery based on
                  diagnostics, practice activities, and lesson feedback.
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
                <section className="mt-6 rounded-2xl border border-[#dce4ef] bg-white p-4">
                  <h4 className="text-base font-black text-[#14213d]">
                    Current Skill Scores
                  </h4>
                  <p className="mt-2 leading-7 text-[#60708a]">
                    These scores represent your current English mastery and may
                    be updated by:
                  </p>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-[#42536b]">
                    <li>Diagnostic assessments</li>
                    <li>Speaking practice</li>
                    <li>Listening activities</li>
                    <li>Teacher feedback</li>
                  </ul>
                </section>
              </section>
              <section className="mt-6">
                <h3 className="text-lg font-black text-[#14213d]">
                  Why this lesson?
                </h3>
                <p className="mt-2 leading-7 text-[#60708a]">
                  {recommendationCopy?.detail}
                </p>
              </section>
              <Button
                className="mt-6"
                href={`/feedback?moduleId=${recommendation.recommended_module.id}`}
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
