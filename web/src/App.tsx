import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { NavLink, Route, Routes, useLocation } from "react-router";
import { getStatus, setAuthHandlers, type Status } from "./api";
import NamePrompt from "./components/NamePrompt";
import AddExpense from "./pages/AddExpense";
import ExpenseDetailPage from "./pages/ExpenseDetail";
import Expenses from "./pages/Expenses";
import SignIn from "./pages/SignIn";
import { supabase } from "./supabase";

const ICONS = {
  add: "M12 5v14M5 12h14",
  expenses: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
  dashboard: "M5 20V11M12 20V4M19 20v-6",
  settings: "M4 7h10M18 7h2M4 17h2M10 17h10M16 5v4M8 15v4",
};

const PAGES = [
  { path: "/", label: "Add", icon: ICONS.add, title: "Add Expense", next: "" },
  { path: "/expenses", label: "Expenses", icon: ICONS.expenses, title: "Expenses", next: "" },
  { path: "/dashboard", label: "Dashboard", icon: ICONS.dashboard, title: "Dashboard", next: "Charts and insights arrive in M10." },
  { path: "/settings", label: "Settings", icon: ICONS.settings, title: "Settings", next: "Settings arrive in M11." },
];

function Icon({ path }: { path: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="size-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={path} />
    </svg>
  );
}

function Logo() {
  return (
    <p className="flex items-center gap-2.5 text-lg font-semibold tracking-tight">
      <span aria-hidden="true" className="grid size-7 place-items-center rounded-lg bg-mint text-sm font-bold text-pine">
        S
      </span>
      SnapSpend
    </p>
  );
}

function Placeholder({ title, next }: { title: string; next: string }) {
  return (
    <section>
      <h1 className="text-3xl font-semibold tracking-tight text-pine">{title}</h1>
      <div className="mt-6 rounded-2xl border border-line p-6">
        <p className="text-muted">{next}</p>
      </div>
    </section>
  );
}

function Notice({ children }: { children: string }) {
  return (
    <main className="grid min-h-dvh place-items-center p-4">
      <p role="alert" className="max-w-md rounded-xl bg-expense-soft p-4 text-sm text-expense">{children}</p>
    </main>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [apiError, setApiError] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [recovering, setRecovering] = useState(false);

  useEffect(() => {
    getStatus().then(setStatus).catch(() => setApiError(true));
  }, []);

  useEffect(() => {
    if (!supabase) return;
    const client = supabase;
    // Reads the current token per request, so the client's automatic refresh is always used.
    setAuthHandlers(
      async () => (await client.auth.getSession()).data.session?.access_token ?? null,
      () => void client.auth.signOut({ scope: "local" }),
    );
    client.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setSessionLoaded(true);
    });
    const { data } = client.auth.onAuthStateChange((event, next) => {
      if (event === "PASSWORD_RECOVERY") setRecovering(true);
      setSession(next);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  if (apiError) return <Notice>Can't reach the SnapSpend API. Check that it's running, then refresh this page.</Notice>;
  if (!status) return null;

  if (status.auth_mode === "local") return <Shell status={status} />;
  if (!supabase) return <Notice>Sign-in isn't set up on this site yet, so your data can't be opened.</Notice>;
  if (!sessionLoaded) return null;
  if (!session || recovering) {
    return <SignIn client={supabase} recovering={recovering} onRecovered={() => setRecovering(false)} />;
  }
  // Keyed by user, so nothing from one account's screens can carry over to the next.
  const { first_name: first, last_name: last, full_name: full } = session.user.user_metadata;
  const name = [first, last].filter(Boolean).join(" ") || full || "";
  return (
    <Shell
      key={session.user.id}
      status={status}
      name={name}
      email={session.user.email}
      onSignOut={() => void supabase?.auth.signOut()}
    />
  );
}

function Shell({ status, name, email, onSignOut }: { status: Status; name?: string; email?: string; onSignOut?: () => void }) {
  const { pathname } = useLocation();

  return (
    <div className="min-h-dvh md:pl-60">
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col bg-pine px-4 py-6 text-white md:flex">
        <div className="px-3">
          <Logo />
        </div>
        <nav aria-label="Main" className="mt-8 flex flex-col gap-1">
          {PAGES.map((page) => (
            <NavLink
              key={page.path}
              to={page.path}
              end={page.path === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive ? "bg-mint text-pine" : "text-white/75 hover:bg-white/10 hover:text-white"
                }`
              }
            >
              <Icon path={page.icon} />
              {page.label}
            </NavLink>
          ))}
        </nav>
        {onSignOut && (
          <div className="mt-auto border-t border-white/15 px-3 pt-4">
            <p className="truncate text-sm font-medium text-white">{name || email}</p>
            <button onClick={onSignOut} className="mt-2 text-sm font-medium text-mint hover:underline">Sign out</button>
          </div>
        )}
      </aside>

      <header className="flex items-center justify-between border-b border-line px-4 py-3 text-pine md:hidden">
        <Logo />
        {onSignOut && (
          <div className="flex min-w-0 items-center gap-3 pl-3">
            <p className="truncate text-sm text-muted">{name || email}</p>
            <button onClick={onSignOut} className="shrink-0 text-sm font-medium text-forest">Sign out</button>
          </div>
        )}
      </header>

      <div className="mx-auto max-w-4xl px-4 pt-6 pb-24 md:px-10 md:pt-10 md:pb-10">
        {onSignOut && !name && <NamePrompt />}
        {status.mock_mode && (
          <p role="status" className="mb-4 rounded-xl bg-mint p-3 text-sm font-semibold text-pine">
            MOCK MODE — extraction is simulated
          </p>
        )}
        {!status.tesseract_available && (
          <p role="status" className="mb-4 rounded-xl bg-mint p-3 text-sm text-pine">
            <strong>Tesseract OCR not found.</strong> Photo and scanned-PDF reading is disabled; manual entry, PDFs with
            a text layer, and the dashboard still work. {status.tesseract_help}
          </p>
        )}

        <main>
          {/* Stays mounted, so visiting another page doesn't lose an unsaved expense. */}
          <div hidden={pathname !== "/"}>
            <AddExpense localMode={status.auth_mode === "local"} />
          </div>
          <Routes>
            <Route path="/" element={null} />
            <Route path="/expenses" element={<Expenses />} />
            <Route path="/expenses/:id" element={<ExpenseDetailPage />} />
            {PAGES.slice(2).map((page) => (
              <Route key={page.path} path={page.path} element={<Placeholder title={page.title} next={page.next} />} />
            ))}
          </Routes>
        </main>
      </div>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 grid grid-cols-4 border-t border-line bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {PAGES.map((page) => (
          <NavLink
            key={page.path}
            to={page.path}
            end={page.path === "/"}
            className={({ isActive }) =>
              `flex flex-col items-center gap-1 py-2 text-xs font-medium ${isActive ? "text-forest" : "text-muted"}`
            }
          >
            {({ isActive }) => (
              <>
                <span className={`rounded-full px-4 py-1 ${isActive ? "bg-mint text-pine" : ""}`}>
                  <Icon path={page.icon} />
                </span>
                {page.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
