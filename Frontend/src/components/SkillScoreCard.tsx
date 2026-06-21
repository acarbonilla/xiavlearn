import Card from "./Card";

export default function SkillScoreCard({
  skill,
  score,
  status,
  diagnosticType,
}: {
  skill: string;
  score: number | string;
  status?: string;
  diagnosticType: string;
}) {
  const numericScore = Math.max(0, Math.min(100, Number(score)));

  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="inline-flex rounded-full bg-[#eff6ff] px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-[#335cff]">
            Official Diagnostic Score
          </p>
          <p className="font-bold">{skill}</p>
          <p className="mt-1 text-sm font-semibold text-[#335cff]">
            {diagnosticType}
          </p>
          {status ? <p className="mt-1 text-sm text-[#60708a]">{status}</p> : null}
        </div>
        <strong className="text-2xl text-[#335cff]">{numericScore}%</strong>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#e8edf5]">
        <div
          className="h-full rounded-full bg-[#20b486]"
          style={{ width: `${numericScore}%` }}
        />
      </div>
    </Card>
  );
}
