"use client";

import { useEffect, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import SkillScoreCard from "@/components/SkillScoreCard";
import type { TeacherFeedback } from "@/lib/api";

export default function FeedbackPage() {
  const [feedback, setFeedback] = useState<TeacherFeedback | null>(null);

  useEffect(() => {
    const stored = sessionStorage.getItem("xiav-feedback");
    if (stored) {
      try {
        const parsedFeedback = JSON.parse(stored) as TeacherFeedback;
        queueMicrotask(() => setFeedback(parsedFeedback));
      } catch {
        sessionStorage.removeItem("xiav-feedback");
      }
    }
  }, []);

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 4</p>
      <h1 className="page-title">Lesson feedback</h1>

      {feedback ? (
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          <Card className="bg-[#14213d] text-white">
            <p className="text-sm font-bold text-[#aebbe8]">Lesson score</p>
            <p className="mt-2 text-6xl font-black">{feedback.score}%</p>
            <h2 className="mt-6 text-xl font-bold">Teacher feedback</h2>
            <p className="mt-2 leading-7 text-[#d6def1]">{feedback.feedback}</p>
          </Card>
          <div className="grid gap-5">
            <SkillScoreCard
              score={feedback.updated_mastery.score}
              skill={feedback.updated_mastery.skill}
              status={feedback.updated_mastery.status}
            />
            <Button href="/study-plan">Generate Study Plan</Button>
          </div>
        </div>
      ) : (
        <Card className="mt-8 max-w-2xl">
          <h2 className="text-xl font-bold">No lesson feedback yet</h2>
          <p className="mt-3 text-[#60708a]">
            Complete a recommended lesson to see your score and updated mastery.
          </p>
          <Button className="mt-5" href="/recommendation">
            Find a Lesson
          </Button>
        </Card>
      )}
    </main>
  );
}
