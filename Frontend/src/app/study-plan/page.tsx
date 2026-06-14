"use client";

import { useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  type CoachSummary,
  type StudyPlanData,
  generateStudyPlan,
  getCoachSummary,
} from "@/lib/api";

export default function StudyPlanPage() {
  const [plan, setPlan] = useState<StudyPlanData | null>(null);
  const [coach, setCoach] = useState<CoachSummary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function buildPlan() {
    setError("");
    setLoading(true);
    try {
      const generatedPlan = await generateStudyPlan();
      setPlan(generatedPlan);
      setCoach(await getCoachSummary());
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 5</p>
      <h1 className="page-title">Study plan and coach summary</h1>
      <p className="page-copy">
        Build a focused weekly plan from your latest mastery scores and lesson
        activity.
      </p>

      {!plan ? (
        <Card className="mt-8 max-w-2xl">
          <h2 className="text-xl font-bold">Ready for your next week?</h2>
          <p className="mt-3 text-[#60708a]">
            XiAv Learn will prioritize the skills that currently need the most
            practice.
          </p>
          {error ? <div className="error-box">{error}</div> : null}
          <Button className="mt-5" disabled={loading} onClick={buildPlan}>
            {loading ? "Generating plan..." : "Generate Study Plan"}
          </Button>
        </Card>
      ) : (
        <div className="mt-8 grid gap-5 lg:grid-cols-2">
          <Card>
            <h2 className="text-2xl font-bold">Weekly plan</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {plan.plan.focus.map((skill) => (
                <span
                  className="rounded-full bg-[#e9eeff] px-3 py-1 text-sm font-bold text-[#335cff]"
                  key={skill}
                >
                  Focus: {skill}
                </span>
              ))}
            </div>
            <ol className="mt-6 grid gap-3">
              {plan.plan.days.map((day) => (
                <li
                  className="rounded-xl border border-[#dce4ef] bg-[#fbfdff] p-4"
                  key={day}
                >
                  {day}
                </li>
              ))}
            </ol>
          </Card>
          <Card className="bg-[#14213d] text-white">
            <p className="text-sm font-bold uppercase tracking-wider text-[#8fa4ff]">
              Coach summary
            </p>
            <h2 className="mt-4 text-2xl font-bold">
              {coach?.summary ?? "Loading coaching guidance..."}
            </h2>
            {coach ? (
              <>
                <p className="mt-6 text-sm font-bold text-[#aebbe8]">Next step</p>
                <p className="mt-2 leading-7 text-[#d6def1]">{coach.next_step}</p>
                <Button className="mt-6" href="/dashboard">
                  Return to Dashboard
                </Button>
              </>
            ) : null}
          </Card>
        </div>
      )}
    </main>
  );
}
