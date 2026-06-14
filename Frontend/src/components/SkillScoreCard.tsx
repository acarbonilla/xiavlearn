import Card from "./Card";

export default function SkillScoreCard({
  skill,
  score,
  status,
}: {
  skill: string;
  score: number | string;
  status?: string;
}) {
  const numericScore = Math.max(0, Math.min(100, Number(score)));

  return (
    <Card>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="font-bold">{skill}</p>
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
