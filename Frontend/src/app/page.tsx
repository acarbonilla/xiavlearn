import Button from "@/components/Button";
import Card from "@/components/Card";

const agents = [
  ["Diagnostic Agent", "Finds your current level and skill gaps."],
  ["Curriculum Agent", "Chooses the next module for your needs."],
  ["Teacher Agent", "Guides practice and gives immediate feedback."],
  ["Coach Agent", "Turns your progress into a practical next step."],
];

export default function Home() {
  return (
    <main className="page-shell">
      <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
        <section>
          <p className="eyebrow">Personalized English learning</p>
          <h1 className="page-title">AI-Powered Personalized Learning Journey</h1>
          <p className="page-copy">
            XiAv Learn coordinates specialized learning agents to diagnose your
            skills, recommend the right lesson, coach your practice, and build a
            study plan around your progress.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Button href="/login">Start Learning</Button>
            <Button href="/dashboard" variant="secondary">
              View Dashboard
            </Button>
          </div>
        </section>
        <Card className="bg-[#14213d] text-white">
          <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#8fa4ff]">
            One connected journey
          </p>
          <div className="mt-5 grid gap-4">
            {agents.map(([title, copy], index) => (
              <div className="flex gap-4" key={title}>
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#335cff] text-sm font-black">
                  {index + 1}
                </span>
                <div>
                  <h2 className="font-bold">{title}</h2>
                  <p className="mt-1 text-sm leading-6 text-[#c8d2e7]">{copy}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </main>
  );
}
