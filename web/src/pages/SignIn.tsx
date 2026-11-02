import { useRef, useState, type FormEvent } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { googleEnabled } from "../supabase";

type Mode = "sign-in" | "sign-up" | "reset" | "new-password";

const TITLES: Record<Mode, { title: string; action: string }> = {
  "sign-in": { title: "Welcome back", action: "Sign in" },
  "sign-up": { title: "Create your account", action: "Create account" },
  reset: { title: "Reset your password", action: "Send reset link" },
  "new-password": { title: "Choose a new password", action: "Save password" },
};

const MIN_PASSWORD = 8;
const inputClass = "mt-1 w-full rounded-xl border border-line px-3 py-2.5 text-base focus:border-forest";

export default function SignIn({ client, recovering, onRecovered }: {
  client: SupabaseClient;
  recovering: boolean;
  onRecovered: () => void;
}) {
  const [chosenMode, setMode] = useState<Mode>("sign-in");
  const mode = recovering ? "new-password" : chosenMode;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [checkConfirm, setCheckConfirm] = useState(false);
  const confirmInput = useRef<HTMLInputElement>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function switchTo(next: Mode) {
    setMode(next);
    setConfirmPassword("");
    setCheckConfirm(false);
    setError("");
    setNotice("");
  }

  const needsConfirm = mode === "sign-up" || mode === "new-password";
  const passwordsDiffer = needsConfirm && password !== confirmPassword;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (passwordsDiffer) {
      setCheckConfirm(true);
      confirmInput.current?.focus();
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "sign-in") {
        const { error } = await client.auth.signInWithPassword({ email, password });
        if (error) setError("That email and password don't match, or the email isn't confirmed yet.");
      } else if (mode === "sign-up") {
        const { error } = await client.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: window.location.origin,
            data: { first_name: firstName.trim(), last_name: lastName.trim() },
          },
        });
        if (error) setError(error.message);
        else setNotice("Check your email for a link to confirm your account.");
      } else if (mode === "reset") {
        const { error } = await client.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
        if (error) setError(error.message);
        else setNotice("If that email has an account, a reset link is on its way.");
      } else {
        const { error } = await client.auth.updateUser({ password });
        if (error) setError(error.message);
        else onRecovered();
      }
    } catch {
      setError("Can't reach the sign-in service. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function signInWithGoogle() {
    setError("");
    const { error } = await client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (error) setError("Google sign-in isn't available right now. Try your email and password.");
  }

  const needsEmail = mode !== "new-password";
  const needsPassword = mode !== "reset";

  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <aside className="hidden flex-col justify-between bg-pine p-12 text-white lg:flex">
        <p className="text-3xl font-semibold tracking-tight">Tabby</p>
        <div>
          <p className="max-w-md text-4xl font-semibold tracking-tight">Snap a receipt. Check it. Know where your money went.</p>
          <p className="mt-4 max-w-md text-white/75">
            Your receipt is read and then discarded. Only the details you confirm are saved, in your private account.
          </p>
        </div>
        <span aria-hidden="true" className="h-1.5 w-16 rounded-full bg-sage" />
      </aside>

      <main className="flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm">
          <p className="mb-8 text-2xl font-semibold tracking-tight text-pine lg:hidden">Tabby</p>
          <h1 className="text-3xl font-semibold tracking-tight text-pine">{TITLES[mode].title}</h1>

          {error && <p role="alert" className="mt-4 rounded-xl bg-expense-soft p-3 text-sm text-expense">{error}</p>}
          {notice && <p role="status" className="mt-4 rounded-xl bg-mint p-3 text-sm text-pine">{notice}</p>}

          <form onSubmit={submit} className="mt-6 space-y-4">
            {mode === "sign-up" && (
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm font-medium text-pine">
                  First name
                  <input
                    required
                    pattern=".*\S.*"
                    title="Enter your first name."
                    maxLength={100}
                    autoComplete="given-name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    className={inputClass}
                  />
                </label>
                <label className="block text-sm font-medium text-pine">
                  Last name
                  <input
                    required
                    pattern=".*\S.*"
                    title="Enter your last name."
                    maxLength={100}
                    autoComplete="family-name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    className={inputClass}
                  />
                </label>
              </div>
            )}
            {needsEmail && (
              <label className="block text-sm font-medium text-pine">
                Email
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={inputClass}
                />
              </label>
            )}
            {needsPassword && (
              <label className="block text-sm font-medium text-pine">
                {mode === "new-password" ? "New password" : "Password"}
                <input
                  type="password"
                  required
                  minLength={mode === "sign-in" ? undefined : MIN_PASSWORD}
                  autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputClass}
                />
              </label>
            )}
            {needsConfirm && (
              <div>
                <label className="block text-sm font-medium text-pine">
                  Confirm password
                  <input
                    ref={confirmInput}
                    type="password"
                    required
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    onBlur={() => setCheckConfirm(confirmPassword !== "")}
                    aria-invalid={checkConfirm && passwordsDiffer}
                    aria-describedby={checkConfirm && passwordsDiffer ? "confirm-password-error" : undefined}
                    className={inputClass}
                  />
                </label>
                {checkConfirm && passwordsDiffer && (
                  <p id="confirm-password-error" role="alert" className="mt-1 text-sm text-expense">Passwords don't match.</p>
                )}
              </div>
            )}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-forest px-4 py-3 font-medium text-white transition-colors hover:bg-pine disabled:opacity-60"
            >
              {busy ? "One moment…" : TITLES[mode].action}
            </button>
          </form>

          {googleEnabled && (mode === "sign-in" || mode === "sign-up") && (
            <button
              type="button"
              onClick={signInWithGoogle}
              className="mt-3 w-full rounded-xl border border-line px-4 py-3 font-medium text-pine transition-colors hover:bg-mint"
            >
              Continue with Google
            </button>
          )}

          <div className="mt-6 flex flex-wrap justify-between gap-2 text-sm">
            {mode === "sign-in" && (
              <>
                <button type="button" onClick={() => switchTo("sign-up")} className="font-medium text-forest hover:underline">
                  Create an account
                </button>
                <button type="button" onClick={() => switchTo("reset")} className="text-muted hover:underline">
                  Forgot password?
                </button>
              </>
            )}
            {(mode === "sign-up" || mode === "reset") && (
              <button type="button" onClick={() => switchTo("sign-in")} className="font-medium text-forest hover:underline">
                Back to sign in
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
