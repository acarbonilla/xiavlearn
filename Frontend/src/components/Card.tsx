import type { ReactNode } from "react";

export default function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border border-[#dce4ef] bg-white p-6 shadow-[0_12px_35px_rgba(20,33,61,0.06)] ${className}`}
    >
      {children}
    </section>
  );
}
