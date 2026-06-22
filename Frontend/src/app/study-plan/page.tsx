"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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

  useEffect(() => {
    const refreshRequested =
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("refresh") === "1";
    if (refreshRequested && !plan && !loading) {
      const timer = window.setTimeout(() => {
        void buildPlan();
      }, 0);
      return () => window.clearTimeout(timer);
    }
  }, [loading, plan]);

  function itemSummary(item: StudyPlanData["plan"]["items"][number]) {
    if (item.skill === "Listening") {
      return "Open your listening teacher session for passage-based comprehension practice.";
    }
    if (item.skill === "Pronunciation") {
      return "Open your pronunciation teacher session for official-level speaking-sound practice.";
    }
    if (item.skill === "Speaking") {
      return "Open your speaking teacher session for guided spoken-answer practice with AI feedback.";
    }
    if (item.module_id) {
      return "Open this guided lesson and continue your weekly focus.";
    }
    return "Open your recommendation to choose the next lesson.";
  }

  function itemActionLabel(item: StudyPlanData["plan"]["items"][number]) {
    if (item.skill === "Listening") {
      return "Start Listening Session";
    }
    if (item.skill === "Pronunciation") {
      return "Start Pronunciation Session";
    }
    if (item.skill === "Speaking") {
      return "Start Speaking Session";
    }
    if (item.module_id) {
      return "Open lesson";
    }
    return "View recommendation";
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 5</p>
      <h1 className="page-title">Study plan and coach summary</h1>
      <p className="page-copy">
        Build a focused weekly plan from your latest official mastery scores.
      </p>

      {!plan ? (
        <Card className="mt-8 max-w-2xl">
          <h2 className="text-xl font-bold">Ready for your next week?</h2>
          <p className="mt-3 text-[#60708a]">
            XiAv Learn will prioritize the official skills that currently need
            the most support.
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
              {plan.plan.items.map((item) => (
                <li key={item.day}>
                  <Link
                    className="block rounded-xl border border-[#dce4ef] bg-[#fbfdff] p-4 transition hover:border-[#335cff] hover:bg-[#f4f7ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#335cff] focus-visible:ring-offset-2"
                    href={item.href}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                        {item.day}
                      </p>
                      <span className="rounded-full bg-[#e9eeff] px-3 py-1 text-xs font-bold text-[#335cff]">
                        {item.fallback_used
                          ? `${item.module_level ?? "No module"} Review - ${item.skill}`
                          : item.module_level
                            ? `${item.module_level} - ${item.skill}`
                            : item.skill}
                      </span>
                    </div>
                    <h3 className="mt-3 text-lg font-bold text-[#14213d]">
                      {item.title}
                    </h3>
                    {item.fallback_used && item.module_level ? (
                      <p className="mt-2 rounded-xl border border-[#facc15] bg-[#fffbeb] px-3 py-2 text-sm leading-6 text-[#7c5e10]">
                        {`No ${item.learner_level} module is available yet. Showing ${item.module_level} review lesson.`}
                      </p>
                    ) : null}
                    {item.fallback_used && item.fallback_reason ? (
                      <p className="mt-2 text-sm leading-6 text-[#7c5e10]">
                        {item.fallback_reason}
                      </p>
                    ) : null}
                    <p className="mt-2 text-sm leading-6 text-[#60708a]">
                      {itemSummary(item)}
                    </p>
                    <p className="mt-4 text-sm font-bold text-[#335cff]">
                      {itemActionLabel(item)}
                    </p>
                  </Link>
                </li>
              ))}
            </ol>
          </Card>
          <Card className="bg-[#f4f7ff]">
            <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
              Coach summary
            </p>
            <h2 className="mt-4 text-2xl font-bold text-[#14213d]">
              {coach?.summary ?? "Loading coaching guidance..."}
            </h2>
            {coach ? (
              <>
                <p className="mt-6 text-sm font-bold text-[#42536b]">Next step</p>
                <p className="mt-2 leading-7 text-[#42536b]">{coach.next_step}</p>
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
