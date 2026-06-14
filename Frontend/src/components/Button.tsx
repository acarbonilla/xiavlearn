import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  href?: string;
  variant?: "primary" | "secondary";
};

const styles = {
  primary:
    "inline-flex items-center justify-center rounded-xl bg-[#335cff] px-5 py-3 font-bold text-white transition hover:bg-[#2447d8] disabled:cursor-not-allowed disabled:opacity-60",
  secondary:
    "inline-flex items-center justify-center rounded-xl border border-[#dce4ef] bg-white px-5 py-3 font-bold text-[#14213d] transition hover:border-[#335cff] hover:text-[#335cff]",
};

export default function Button({
  children,
  href,
  variant = "primary",
  className = "",
  ...props
}: ButtonProps) {
  const classes = `${styles[variant]} ${className}`;

  if (href) {
    return (
      <Link className={classes} href={href}>
        {children}
      </Link>
    );
  }

  return (
    <button className={classes} {...props}>
      {children}
    </button>
  );
}
