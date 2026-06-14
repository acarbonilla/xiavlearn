import Link from "next/link";

const links = [
  ["Dashboard", "/dashboard"],
  ["Diagnostic", "/diagnostic"],
  ["Recommendation", "/recommendation"],
  ["Study Plan", "/study-plan"],
];

export default function Header() {
  return (
    <header className="sticky top-0 z-10 border-b border-[#dce4ef] bg-white/90 backdrop-blur">
      <div className="mx-auto flex min-h-16 w-[min(1120px,calc(100%-2rem))] flex-wrap items-center justify-between gap-4 py-3">
        <Link className="text-lg font-black tracking-[-0.03em]" href="/">
          XiAv <span className="text-[#335cff]">Learn</span>
        </Link>
        <nav className="flex flex-wrap items-center gap-4 text-sm font-semibold text-[#60708a]">
          {links.map(([label, href]) => (
            <Link className="transition hover:text-[#335cff]" href={href} key={href}>
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
