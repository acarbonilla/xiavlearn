"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  type FocusEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { type AuthUser, getCurrentUser, logoutUser } from "@/lib/api";

type NavLink = {
  label: string;
  href: string;
};

type NavGroup = {
  label: string;
  links: NavLink[];
};

const topLevelLinks: NavLink[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Recommendation", href: "/recommendation" },
  { label: "Study Plan", href: "/study-plan" },
];

const dropdownGroups: NavGroup[] = [
  {
    label: "Assessment",
    links: [
      { label: "Text Diagnostic", href: "/diagnostic" },
      { label: "Voice Diagnostic", href: "/voice-diagnostic" },
    ],
  },
  {
    label: "Teacher Sessions",
    links: [
      { label: "Speaking Teacher", href: "/speaking-teacher" },
      { label: "Listening Teacher", href: "/listening-teacher" },
      { label: "Pronunciation Teacher", href: "/pronunciation-teacher" },
      { label: "Voice Conversation", href: "/voice-conversation" },
    ],
  },
];

const publicRoutes = new Set(["/", "/login", "/signup"]);
const navItemClass =
  "rounded-full px-3 py-2 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#335cff] focus-visible:ring-offset-2";
const accountMenuLabel = "account-menu";

function isActivePath(pathname: string | null, href: string) {
  return pathname === href;
}

export default function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const menuRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const isPublicRoute = pathname ? publicRoutes.has(pathname) : false;

  const refreshUser = useCallback(() => {
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (isPublicRoute) {
      return;
    }

    refreshUser();
    window.addEventListener("xiav-auth-change", refreshUser);
    return () => window.removeEventListener("xiav-auth-change", refreshUser);
  }, [isPublicRoute, refreshUser]);

  useEffect(() => {
    if (!openMenu) {
      return;
    }

    const menuLabel = openMenu;

    function handlePointerDown(event: MouseEvent) {
      const activeMenu = menuRefs.current[menuLabel];
      if (activeMenu && !activeMenu.contains(event.target as Node)) {
        setOpenMenu(null);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [openMenu]);

  async function handleLogout() {
    setOpenMenu(null);
    await logoutUser();
    setUser(null);
    router.push("/login");
  }

  function handleMenuToggle(label: string) {
    setOpenMenu((current) => (current === label ? null : label));
  }

  function handleMenuKeyDown(event: KeyboardEvent<HTMLButtonElement>, label: string) {
    if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
      event.preventDefault();
      setOpenMenu(label);
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setOpenMenu(null);
    }
  }

  function handleMenuBlur(event: FocusEvent<HTMLDivElement>, label: string) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setOpenMenu((current) => (current === label ? null : current));
    }
  }

  const activeUser = isPublicRoute ? null : user;

  return (
    <header className="sticky top-0 z-10 border-b border-[#dce4ef] bg-white/90 backdrop-blur">
      <div className="mx-auto flex min-h-16 w-[min(1120px,calc(100%-2rem))] flex-wrap items-center justify-between gap-4 py-3">
        <Link className="text-lg font-black tracking-[-0.03em]" href="/">
          XiAv <span className="text-[#335cff]">Learn</span>
        </Link>
        <nav className="flex flex-wrap items-center justify-end gap-2 text-sm font-semibold text-[#60708a]">
          {topLevelLinks.map(({ label, href }) => {
            const isActive = isActivePath(pathname, href);

            return (
              <Link
                className={`${navItemClass} ${
                  isActive
                    ? "bg-[#eef3ff] text-[#335cff]"
                    : "text-[#60708a] hover:bg-[#f5f8ff] hover:text-[#335cff]"
                }`}
                href={href}
                key={href}
              >
                {label}
              </Link>
            );
          })}
          {dropdownGroups.map((group) => {
            const isGroupActive = group.links.some((link) => isActivePath(pathname, link.href));
            const isOpen = openMenu === group.label;
            const menuId = `${group.label.toLowerCase().replace(/\s+/g, "-")}-menu`;

            return (
              <div
                className="relative"
                key={group.label}
                onBlur={(event) => handleMenuBlur(event, group.label)}
                onMouseEnter={() => setOpenMenu(group.label)}
                onMouseLeave={() => setOpenMenu((current) => (current === group.label ? null : current))}
                ref={(node) => {
                  menuRefs.current[group.label] = node;
                }}
              >
                <button
                  aria-controls={menuId}
                  aria-expanded={isOpen}
                  aria-haspopup="menu"
                  className={`${navItemClass} inline-flex items-center gap-2 ${
                    isGroupActive || isOpen
                      ? "bg-[#eef3ff] text-[#335cff]"
                      : "text-[#60708a] hover:bg-[#f5f8ff] hover:text-[#335cff]"
                  }`}
                  onClick={() => handleMenuToggle(group.label)}
                  onKeyDown={(event) => handleMenuKeyDown(event, group.label)}
                  type="button"
                >
                  {group.label}
                  <svg
                    aria-hidden="true"
                    className={`h-3 w-3 transition-transform ${isOpen ? "rotate-180" : ""}`}
                    viewBox="0 0 12 12"
                  >
                    <path
                      d="M3 4.5 6 7.5l3-3"
                      fill="none"
                      stroke="currentColor"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="1.5"
                    />
                  </svg>
                </button>
                {isOpen ? (
                  <>
                    <div aria-hidden="true" className="absolute left-0 top-full h-2 min-w-56" />
                    <div
                      className="absolute left-0 top-full z-20 mt-2 min-w-56 rounded-2xl border border-[#dce4ef] bg-white p-2 shadow-[0_18px_45px_rgba(20,33,61,0.12)]"
                      id={menuId}
                      role="menu"
                    >
                      {group.links.map((link) => {
                        const isActive = isActivePath(pathname, link.href);

                        return (
                          <Link
                            className={`block rounded-xl px-3 py-2 transition ${
                              isActive
                                ? "bg-[#eef3ff] text-[#335cff]"
                                : "text-[#60708a] hover:bg-[#f5f8ff] hover:text-[#335cff]"
                            }`}
                            href={link.href}
                            key={link.href}
                            onClick={() => setOpenMenu(null)}
                            role="menuitem"
                          >
                            {link.label}
                          </Link>
                        );
                      })}
                    </div>
                  </>
                ) : null}
              </div>
            );
          })}
          {activeUser ? (
            (() => {
              const isOpen = openMenu === accountMenuLabel;

              return (
                <div
                  className="relative"
                  onBlur={(event) => handleMenuBlur(event, accountMenuLabel)}
                  onMouseEnter={() => setOpenMenu(accountMenuLabel)}
                  onMouseLeave={() =>
                    setOpenMenu((current) => (current === accountMenuLabel ? null : current))
                  }
                  ref={(node) => {
                    menuRefs.current[accountMenuLabel] = node;
                  }}
                >
                  <button
                    aria-controls={accountMenuLabel}
                    aria-expanded={isOpen}
                    aria-haspopup="menu"
                    className={`${navItemClass} inline-flex items-center gap-2 ${
                      isOpen
                        ? "bg-[#eef3ff] text-[#335cff]"
                        : "text-[#14213d] hover:bg-[#f5f8ff] hover:text-[#335cff]"
                    }`}
                    onClick={() => handleMenuToggle(accountMenuLabel)}
                    onKeyDown={(event) => handleMenuKeyDown(event, accountMenuLabel)}
                    type="button"
                  >
                    {activeUser.username}
                    <svg
                      aria-hidden="true"
                      className={`h-3 w-3 transition-transform ${isOpen ? "rotate-180" : ""}`}
                      viewBox="0 0 12 12"
                    >
                      <path
                        d="M3 4.5 6 7.5l3-3"
                        fill="none"
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.5"
                      />
                    </svg>
                  </button>
                  {isOpen ? (
                    <>
                      <div aria-hidden="true" className="absolute right-0 top-full h-2 min-w-56" />
                      <div
                        className="absolute right-0 top-full z-20 mt-2 min-w-56 rounded-2xl border border-[#dce4ef] bg-white p-2 shadow-[0_18px_45px_rgba(20,33,61,0.12)]"
                        id={accountMenuLabel}
                        role="menu"
                      >
                        <div className="rounded-xl px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#60708a]">
                          Signed in as
                        </div>
                        <div className="rounded-xl px-3 pb-2 text-sm font-semibold text-[#14213d]">
                          {activeUser.username}
                        </div>
                        <button
                          className="block w-full rounded-xl px-3 py-2 text-left text-[#335cff] transition hover:bg-[#f5f8ff]"
                          onClick={handleLogout}
                          role="menuitem"
                          type="button"
                        >
                          Logout
                        </button>
                      </div>
                    </>
                  ) : null}
                </div>
              );
            })()
          ) : (
            <>
              <Link
                className={`${navItemClass} text-[#60708a] hover:bg-[#f5f8ff] hover:text-[#335cff]`}
                href="/login"
              >
                Login
              </Link>
              <Link className={`${navItemClass} bg-[#335cff] text-white hover:bg-[#2447d8]`} href="/signup">
                Sign Up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
