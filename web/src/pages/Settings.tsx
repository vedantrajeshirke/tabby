import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, deleteAccount, getSettings, loadDemoData, removeDemoData, saveSettings, type UserSettings } from "../api";
import { localToday, parseAmount } from "../format";
import { supabase } from "../supabase";

const inputClass = "mt-1 w-full rounded-xl border border-line bg-white px-3 py-2.5 text-base focus:border-forest";
const secondaryButton = "rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-pine transition-colors hover:bg-mint disabled:opacity-60";
const CONFIRM_WORD = "DELETE";

function Panel({ title, intro, children }: { title: string; intro?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line p-5 md:p-6">
      <h2 className="font-semibold tracking-tight text-pine">{title}</h2>
      {intro && <p className="mt-1 text-sm text-muted">{intro}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function message(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback;
}

export default function SettingsPage({ signedIn, firstName, lastName, email, hasPassword }: {
  signedIn: boolean;
  firstName: string;
  lastName: string;
  email?: string;
  hasPassword: boolean;
}) {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setError("");
    getSettings().then(setSettings).catch((e) => setError(message(e, "Couldn't load your settings. Please try again.")));
  }, [attempt]);

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="pb-2 text-3xl font-semibold tracking-tight text-pine">Settings</h1>
      {error && (
        <div role="alert" className="rounded-xl bg-expense-soft p-4 text-sm text-expense">
          <p>{error}</p>
          <button onClick={() => setAttempt((n) => n + 1)} className="mt-2 font-medium underline">Try again</button>
        </div>
      )}
      {!error && !settings && <p role="status" className="text-muted">Loading your settings…</p>}
      {settings && (
        <>
          <ProfileAndBudget initial={settings} signedIn={signedIn} firstName={firstName} lastName={lastName} onSaved={setSettings} />
          <DemoData />
          <DeleteEverything signedIn={signedIn} email={email} hasPassword={hasPassword} />
        </>
      )}
    </div>
  );
}

function ProfileAndBudget({ initial, signedIn, firstName, lastName, onSaved }: {
  initial: UserSettings;
  signedIn: boolean;
  firstName: string;
  lastName: string;
  onSaved: (settings: UserSettings) => void;
}) {
  const [first, setFirst] = useState(signedIn ? firstName : initial.name);
  const [last, setLast] = useState(lastName);
  const [budget, setBudget] = useState(initial.monthly_budget == null ? "" : initial.monthly_budget.toFixed(2));
  const [cycleDay, setCycleDay] = useState(initial.cycle_start_day);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const parsedBudget = parseAmount(budget);
  const budgetProblem = Number.isNaN(parsedBudget) ? "Enter a number, like 800." : parsedBudget !== null && parsedBudget < 0 ? "A budget can't be negative." : "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (budgetProblem) return;
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      onSaved(await saveSettings({ name: first.trim(), monthly_budget: parsedBudget, cycle_start_day: cycleDay }));
      if (signedIn && (first.trim() !== firstName || last.trim() !== lastName)) {
        const result = await supabase?.auth.updateUser({ data: { first_name: first.trim(), last_name: last.trim() } });
        if (result?.error) throw new Error("name");
      }
      setSaved(true);
    } catch (e) {
      setError(message(e, "Your settings were saved, but your name couldn't be updated. Please try again."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel title="Profile and budget">
      <form onSubmit={submit} className="space-y-4">
        {signedIn ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-medium text-pine">
              First name
              <input maxLength={100} autoComplete="given-name" value={first} onChange={(e) => setFirst(e.target.value)} className={inputClass} />
            </label>
            <label className="block text-sm font-medium text-pine">
              Last name
              <input maxLength={100} autoComplete="family-name" value={last} onChange={(e) => setLast(e.target.value)} className={inputClass} />
            </label>
          </div>
        ) : (
          <label className="block text-sm font-medium text-pine">
            Name
            <input maxLength={100} autoComplete="given-name" value={first} onChange={(e) => setFirst(e.target.value)} className={inputClass} />
            <span className="mt-1 block text-xs font-normal text-muted">Used to greet you in your insights.</span>
          </label>
        )}
        <label className="block text-sm font-medium text-pine">
          Monthly budget (USD)
          <input
            inputMode="decimal"
            autoComplete="off"
            aria-invalid={Boolean(budgetProblem)}
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            className={`${inputClass} amount ${budgetProblem ? "border-expense" : ""}`}
          />
          {budgetProblem ? (
            <span className="mt-1 block text-sm font-normal text-expense">{budgetProblem}</span>
          ) : (
            <span className="mt-1 block text-xs font-normal text-muted">Leave empty for no budget.</span>
          )}
        </label>
        <label className="block text-sm font-medium text-pine">
          Budget cycle starts on day
          <select value={cycleDay} onChange={(e) => setCycleDay(Number(e.target.value))} className={inputClass}>
            {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => <option key={day}>{day}</option>)}
          </select>
          <span className="mt-1 block text-xs font-normal text-muted">Useful if your stipend or allowance arrives mid-month.</span>
        </label>
        {error && <p role="alert" className="rounded-xl bg-expense-soft p-3 text-sm text-expense">{error}</p>}
        {saved && <p role="status" className="rounded-xl bg-mint p-3 text-sm text-pine">Settings saved.</p>}
        <button type="submit" disabled={saving || Boolean(budgetProblem)} className="rounded-xl bg-forest px-5 py-2.5 font-medium text-white transition-colors hover:bg-pine disabled:opacity-60">
          {saving ? "Saving…" : "Save settings"}
        </button>
      </form>
    </Panel>
  );
}

function DemoData() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState("");
  const [error, setError] = useState("");

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setResult("");
    setError("");
    try {
      setResult(await action());
    } catch (e) {
      setError(message(e, "That didn't work. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Demo data" intro="Try the dashboard with made-up spending. It's labeled as synthetic everywhere, and your real expenses are never touched.">
      <div className="flex flex-wrap gap-3">
        <button
          disabled={busy}
          onClick={() => run(async () => `Loaded ${(await loadDemoData(localToday())).added} synthetic expenses.`)}
          className={secondaryButton}
        >
          Load synthetic demo data
        </button>
        <button
          disabled={busy}
          onClick={() => run(async () => `Removed ${(await removeDemoData()).removed} synthetic expenses.`)}
          className={secondaryButton}
        >
          Remove synthetic demo data
        </button>
      </div>
      {result && <p role="status" className="mt-3 rounded-xl bg-mint p-3 text-sm text-pine">{result}</p>}
      {error && <p role="alert" className="mt-3 rounded-xl bg-expense-soft p-3 text-sm text-expense">{error}</p>}
    </Panel>
  );
}

function DeleteEverything({ signedIn, email, hasPassword }: { signedIn: boolean; email?: string; hasPassword: boolean }) {
  const usePassword = signedIn && hasPassword && Boolean(email); // local mode and Google accounts have no password
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const confirmed = usePassword ? typed.length > 0 : typed === CONFIRM_WORD;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!confirmed) return;
    setDeleting(true);
    setError("");
    try {
      if (usePassword) {
        // Checked with Supabase directly, so the password never reaches our API.
        const check = await supabase?.auth.signInWithPassword({ email: email!, password: typed });
        if (check?.error) {
          setTyped("");
          setError(check.error.status === 400 ? "That password isn't right. Nothing was deleted." : "Couldn't check your password, so nothing was deleted. Please try again.");
          setDeleting(false);
          return;
        }
      }
      await deleteAccount();
      if (signedIn) await supabase?.auth.signOut({ scope: "local" });
      window.location.assign("/");
    } catch (e) {
      setError(message(e, "Couldn't finish deleting. Please try again."));
      setDeleting(false);
    }
  }

  return (
    <Panel
      title={signedIn ? "Delete my account" : "Delete all my data"}
      intro={signedIn
        ? "Permanently removes your expenses, settings and sign-in. This can't be undone."
        : "Permanently removes every expense and setting on this device. This can't be undone."}
    >
      <form onSubmit={submit}>
        <label className="block text-sm font-medium text-pine">
          {usePassword ? "Enter your password to confirm" : `Type ${CONFIRM_WORD} to confirm`}
          <input
            type={usePassword ? "password" : "text"}
            autoComplete={usePassword ? "current-password" : "off"}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            className={inputClass}
          />
        </label>
        {error && <p role="alert" className="mt-3 rounded-xl bg-expense-soft p-3 text-sm text-expense">{error}</p>}
        <button
          type="submit"
          disabled={!confirmed || deleting}
          className="mt-3 rounded-xl bg-expense px-5 py-2.5 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {deleting ? "Deleting…" : "Delete permanently"}
        </button>
      </form>
    </Panel>
  );
}
