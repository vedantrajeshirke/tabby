import { useState, type FormEvent } from "react";
import { supabase } from "../supabase";

const inputClass = "mt-1 w-full rounded-xl border border-line bg-white px-3 py-2 text-base focus:border-forest";

/** For accounts created before names were asked for. */
export default function NamePrompt() {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await supabase?.auth.updateUser({ data: { first_name: firstName.trim(), last_name: lastName.trim() } });
      if (result?.error) setError("Couldn't save your name. Please try again.");
    } catch {
      setError("Couldn't save your name. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mb-6 rounded-2xl border border-line p-4">
      <h2 className="font-medium text-pine">What should we call you?</h2>
      {error && <p role="alert" className="mt-2 text-sm text-expense">{error}</p>}
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block text-sm font-medium text-pine">
          First name
          <input required pattern=".*\S.*" title="Enter your first name." maxLength={100} autoComplete="given-name" value={firstName} onChange={(e) => setFirstName(e.target.value)} className={inputClass} />
        </label>
        <label className="block text-sm font-medium text-pine">
          Last name
          <input required pattern=".*\S.*" title="Enter your last name." maxLength={100} autoComplete="family-name" value={lastName} onChange={(e) => setLastName(e.target.value)} className={inputClass} />
        </label>
      </div>
      <div className="mt-3 flex gap-3">
        <button type="submit" disabled={busy} className="rounded-xl bg-forest px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-pine disabled:opacity-60">
          Save name
        </button>
        <button type="button" onClick={() => setDismissed(true)} className="text-sm font-medium text-muted hover:underline">
          Not now
        </button>
      </div>
    </form>
  );
}
