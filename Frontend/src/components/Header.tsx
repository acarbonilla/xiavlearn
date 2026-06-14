"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { type AuthUser, getCurrentUser, logoutUser } from "@/lib/api";

const links = [
  ["Dashboard", "/dashboard"],
  ["Diagnostic", "/diagnostic"],
  ["Recommendation", "/recommendation"],
  ["Study Plan", "/study-plan"],
];

export default function Header() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);

  const refreshUser = useCallback(() => {
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    refreshUser();
    window.addEventListener("xiav-auth-change", refreshUser);
    return () => window.removeEventListener("xiav-auth-change", refreshUser);
  }, [refreshUser]);

  async function handleLogout() {
    await logoutUser();
    setUser(null);
    router.push("/login");
  }

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
          {user ? (
            <>
              <span className="text-[#14213d]">{user.username}</span>
              <button
                className="font-semibold text-[#335cff]"
                onClick={handleLogout}
                type="button"
              >
                Logout
              </button>
            </>
          ) : (
            <>
              <Link className="transition hover:text-[#335cff]" href="/login">
                Login
              </Link>
              <Link className="text-[#335cff]" href="/signup">
                Sign Up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
