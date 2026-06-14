"use client";

import { useEffect, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import SkillScoreCard from "@/components/SkillScoreCard";
import { type DashboardData, getDashboard } from "@/lib/api";

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDashboard()
      .then(setDashboard)
      .catch((requestError: Error) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="page-shell">
      <p className="eyebrow">Your learning hub</p>
      <h1 className="page-title">Dashboard</h1>

      {loading ? <p className="page-copy">Loading your progress...</p> : null}
      {error ? <div className="error-box">{error}</div> : null}

      {dashboard ? (
        <div className="mt-8 grid gap-6">
          <div className="grid md:grid-cols-3">
            <Card>
              <p className="text-sm font-bold text-[#60708a]">Current level</p>
              <p className="mt-2 text-4xl font-black text-[#335cff]">
                {dashboard.profile.current_level || "Not assessed"}
              </p>
            </Card>
            <Card className="md:col-span-2">
              <p className="text-sm font-bold text-[#60708a]">
                Recommended module
              </p>
              <h2 className="mt-2 text-2xl font-bold">
                {dashboard.recommended_module?.title ?? "Complete the diagnostic"}
              </h2>
              {dashboard.recommended_module ? (
                <p className="mt-2 text-[#60708a]">
                  {dashboard.recommended_module.level} ·{" "}
                  {dashboard.recommended_module.skill}
                </p>
              ) : null}
            </Card>
          </div>

          <section>
            <h2 className="mb-4 text-2xl font-bold">Skill mastery</h2>
            {dashboard.skill_mastery.length ? (
              <div className="grid md:grid-cols-2 lg:grid-cols-3">
                {dashboard.skill_mastery.map((mastery) => (
                  <SkillScoreCard
                    key={mastery.id}
                    score={mastery.score}
                    skill={mastery.skill.name}
                    status={`${mastery.level_code} · ${mastery.status}`}
                  />
                ))}
              </div>
            ) : (
              <Card>No mastery scores yet. Start with the diagnostic.</Card>
            )}
          </section>

          <div className="grid lg:grid-cols-2">
            <Card>
              <h2 className="text-xl font-bold">Latest study plan</h2>
              {dashboard.latest_study_plan ? (
                <>
                  <p className="mt-2 text-sm text-[#60708a]">
                    {dashboard.latest_study_plan.start_date} to{" "}
                    {dashboard.latest_study_plan.end_date}
                  </p>
                  <ul className="mt-4 grid gap-2">
                    {(dashboard.latest_study_plan.plan_data.days ?? []).map(
                      (day) => (
                        <li key={day}>{day}</li>
                      ),
                    )}
                  </ul>
                </>
              ) : (
                <p className="mt-3 text-[#60708a]">No study plan generated yet.</p>
              )}
            </Card>
            <Card>
              <h2 className="text-xl font-bold">Recent sessions</h2>
              {dashboard.recent_sessions.length ? (
                <ul className="mt-4 grid gap-3">
                  {dashboard.recent_sessions.map((session) => (
                    <li
                      className="flex justify-between gap-4 border-b border-[#edf1f6] pb-3"
                      key={session.id}
                    >
                      <span>{session.module?.title ?? session.session_type}</span>
                      <strong>{session.score ? `${session.score}%` : "In progress"}</strong>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-[#60708a]">No recent sessions.</p>
              )}
            </Card>
          </div>

          <Card className="border-[#bfdbfe] bg-[#eff6ff]">
            <h2 className="text-xl font-bold">Coach summary</h2>
            <p className="mt-2 text-[#60708a]">
              Generate a study plan to receive your latest coaching summary.
            </p>
            <Button className="mt-5" href="/study-plan">
              Open Study Plan
            </Button>
          </Card>
        </div>
      ) : null}
    </main>
  );
}
