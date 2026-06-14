import Button from "@/components/Button";
import Card from "@/components/Card";
import { ADMIN_LOGIN_URL } from "@/lib/api";

export default function LoginPage() {
  return (
    <main className="page-shell">
      <div className="mx-auto max-w-2xl">
        <p className="eyebrow">MVP access</p>
        <h1 className="page-title">Login or register</h1>
        <Card className="mt-8">
          <h2 className="text-xl font-bold">Authentication placeholder</h2>
          <p className="mt-3 leading-7 text-[#60708a]">
            Sprint 4 uses the existing Django session. Log in through Django
            Admin, then return here to begin the learning flow.
          </p>
          <div className="note-box">
            For session cookies to work locally, open both apps with the same
            hostname. Recommended: backend at 127.0.0.1:8000 and frontend at
            127.0.0.1:3000.
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <a
              className="inline-flex items-center justify-center rounded-xl bg-[#335cff] px-5 py-3 font-bold text-white hover:bg-[#2447d8]"
              href={ADMIN_LOGIN_URL}
              rel="noreferrer"
              target="_blank"
            >
              Open Django Admin Login
            </a>
            <Button href="/diagnostic" variant="secondary">
              Continue to Diagnostic
            </Button>
          </div>
        </Card>
      </div>
    </main>
  );
}
