"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

import Card from "@/components/Card";

export default function LessonPage({
  params,
}: {
  params: Promise<{ moduleId: string }>;
}) {
  const { moduleId } = use(params);
  const router = useRouter();
  const numericModuleId = Number(moduleId);
  const hasValidModuleId = Number.isInteger(numericModuleId);
  const error = hasValidModuleId ? "" : "The lesson module ID is invalid.";

  useEffect(() => {
    if (!hasValidModuleId) {
      return;
    }
    router.replace(`/feedback?moduleId=${numericModuleId}`);
  }, [hasValidModuleId, numericModuleId, router]);

  return (
    <main className="page-shell">
      <p className="eyebrow">Step 3</p>
      <h1 className="page-title">Guided lesson</h1>
      {hasValidModuleId ? (
        <p className="page-copy">Redirecting to your teacher session...</p>
      ) : null}
      {error ? <div className="error-box">{error}</div> : null}

      {hasValidModuleId ? (
        <Card className="mt-8">
          <p className="leading-7 text-[#60708a]">
            Your recommended lesson now runs through the guided AI Teacher session.
          </p>
        </Card>
      ) : null}
    </main>
  );
}
