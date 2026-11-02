import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ApiError,
  saveExpense,
  updateExpense,
  validateEdit,
  validateExpense,
  type ExpenseBody,
  type ExpenseDetail,
  type Report,
  type SavedExpense,
  type Upload,
} from "../api";
import { localToday, parseAmount, PAYMENT_METHODS } from "../format";

const VALIDATE_DELAY_MS = 350;
const UNUSABLE = new Set(["unreadable", "not_an_expense"]);
const AMOUNT_FIELDS = ["total", "subtotal", "tax", "tip"] as const;
const TEXT_ERROR = "Enter a number, like 12.50.";

type AmountField = (typeof AMOUNT_FIELDS)[number];
type Values = {
  merchant: string;
  date: string;
  total: string;
  subtotal: string;
  tax: string;
  tip: string;
  payment_method: string;
  note: string;
};

const inputBase = "mt-1 w-full rounded-xl border px-3 py-2.5 text-base bg-white focus:border-forest";

function asText(value: number | null | undefined): string {
  return value == null ? "" : value.toFixed(2);
}

function Field({ label, htmlFor, status, help, error, children }: {
  label: string;
  htmlFor: string;
  status?: "read" | "check";
  help?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="flex items-center gap-2 text-sm font-medium text-pine">
        {label}
        {status === "read" && <span title="Read from your receipt" aria-hidden="true" className="size-1.5 rounded-full bg-sage" />}
        {status === "check" && <span className="rounded-full bg-caution-soft px-2 py-0.5 text-xs font-medium text-caution">Please check</span>}
      </label>
      {children}
      {error && <p className="mt-1 text-sm text-expense">{error}</p>}
      {help && !error && <p className="mt-1 text-xs text-muted">{help}</p>}
    </div>
  );
}

function Preview({ file, url }: { file: File | null; url: string | null }) {
  const [failed, setFailed] = useState(false);
  if (!file || !url) return null;
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-[#f6f9f7] md:sticky md:top-10">
      {isPdf ? (
        <object data={url} type="application/pdf" className="h-72 w-full md:h-[32rem]" aria-label="Your PDF">
          <p className="p-6 text-center text-sm text-muted">This browser can't preview PDFs here. The details were still read.</p>
        </object>
      ) : failed ? (
        <p className="p-6 text-center text-sm text-muted">This browser can't preview this file type. The details were still read.</p>
      ) : (
        <img src={url} alt="Your receipt" onError={() => setFailed(true)} className="max-h-72 w-full object-contain md:max-h-[32rem]" />
      )}
    </div>
  );
}

export default function ConfirmForm({ upload = null, existing, file = null, previewUrl = null, categories, onDiscard, onSaved }: {
  upload?: Upload | null;
  existing?: ExpenseDetail; // set when editing a saved expense
  file?: File | null;
  previewUrl?: string | null;
  categories: string[];
  onDiscard: () => void;
  onSaved: (expense: SavedExpense) => void;
}) {
  const extraction = upload?.extraction ?? null;
  // A failed read starts empty, as manual entry; its text stays available below.
  const prefill = extraction && !UNUSABLE.has(extraction.document_type) ? extraction : null;
  const initial: Values = useMemo(
    () => existing ? {
      merchant: existing.merchant,
      date: existing.date,
      total: asText(existing.total),
      subtotal: asText(existing.subtotal),
      tax: asText(existing.tax),
      tip: asText(existing.tip),
      payment_method: existing.payment_method ?? "",
      note: existing.note ?? "",
    } : ({
      merchant: prefill?.merchant ?? "",
      date: prefill ? upload!.suggested_date : localToday(),
      total: asText(prefill?.total),
      subtotal: asText(prefill?.subtotal),
      tax: asText(prefill?.tax),
      tip: asText(prefill?.tip),
      payment_method: prefill?.payment_method ?? "",
      note: "",
    }),
    [existing, prefill, upload],
  );

  const [values, setValues] = useState(initial);
  const [category, setCategory] = useState<string | null>(null); // null until the user picks one, so suggestions stay live
  const [alwaysUse, setAlwaysUse] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const amounts = useMemo(
    () => Object.fromEntries(AMOUNT_FIELDS.map((f) => [f, parseAmount(values[f])])) as Record<AmountField, number | null>,
    [values],
  );
  const badAmount = AMOUNT_FIELDS.some((f) => Number.isNaN(amounts[f]));
  const canCheck = !badAmount && Boolean(values.date);

  const body: ExpenseBody = useMemo(
    () => ({
      merchant: values.merchant,
      date: values.date,
      ...amounts,
      payment_method: values.payment_method || null,
      note: values.note,
      category,
      always_use_category: alwaysUse,
      client_today: localToday(),
      extraction,
      file_hash: upload?.file_hash ?? null,
    }),
    [values, amounts, category, alwaysUse, extraction, upload],
  );

  const [checking, setChecking] = useState(false);
  useEffect(() => {
    if (!canCheck) return;
    const controller = new AbortController();
    setChecking(true);
    const timer = setTimeout(() => {
      (existing ? validateEdit(existing.id, body, controller.signal) : validateExpense(body, controller.signal))
        .then((result) => {
          setReport(result);
          setChecking(false);
        })
        .catch((e) => {
          if (controller.signal.aborted) return;
          setChecking(false);
          setError(e instanceof ApiError ? e.message : "Couldn't check these details. Please try again.");
        });
    }, VALIDATE_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [body, canCheck, existing]);

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setError("");
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const { expense } = await (existing ? updateExpense(existing.id, body) : saveExpense(body));
      onSaved(expense);
    } catch (e) {
      if (e instanceof ApiError && e.report) setReport(e.report);
      setError(e instanceof ApiError ? e.message : "Couldn't save this expense. Please try again.");
      setSaving(false);
    }
  }

  /** Marks fields read from the receipt. Once edited, a field's confidence and reason no longer apply. */
  function fieldState(key: "merchant" | "date" | AmountField) {
    if (!prefill || values[key] !== initial[key]) return {};
    const confidence = prefill.field_confidence[key];
    return {
      status: confidence === "low" ? ("check" as const) : confidence ? ("read" as const) : undefined,
      help: prefill.field_reason[key],
    };
  }

  function amountInput(key: AmountField, label: string, big = false) {
    const invalid = Number.isNaN(amounts[key]);
    const state = fieldState(key);
    const serverError = report?.issues.some((i) => i.field === key && i.severity === "error");
    return (
      <Field label={label} htmlFor={key} {...state} error={invalid ? TEXT_ERROR : undefined}>
        <input
          id={key}
          inputMode="decimal"
          autoComplete="off"
          value={values[key]}
          aria-invalid={invalid || serverError}
          onChange={(e) => set(key, e.target.value)}
          className={`${inputBase} amount ${big ? "text-2xl font-semibold" : ""} ${
            invalid || serverError ? "border-expense" : state.status === "check" ? "border-caution" : "border-line"
          }`}
        />
      </Field>
    );
  }

  const issues = report?.issues ?? [];
  const blockers = issues.filter((i) => i.severity === "error" && !["V01", "V02"].includes(i.code));
  const warnings = issues.filter((i) => i.severity === "warning");
  const currency = existing?.currency ?? extraction?.currency ?? "USD";
  const canSave = canCheck && !saving && !checking && report !== null && !report.blocks_save;
  const shownCategory = category ?? report?.category ?? existing?.category ?? "";
  const rawText = existing?.extraction?.raw_text ?? extraction?.raw_text;
  const heading = existing ? "Edit expense" : prefill ? "Check the details" : "Enter the details";
  const intro = existing ? "Change anything that's wrong, then save." : prefill ? "Fix anything that looks wrong, then save." : "Add what you know. Only the total and date are needed.";
  const hasPreview = Boolean(file && previewUrl);

  return (
    <section>
      <h1 className="text-3xl font-semibold tracking-tight text-pine">{heading}</h1>
      <p className="mt-2 text-muted">{intro}</p>

      <div className={`mt-6 grid gap-6 ${hasPreview ? "md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]" : "max-w-xl"}`}>
        {hasPreview && <div><Preview file={file} url={previewUrl} /></div>}

        <form
          className="min-w-0 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSave) save();
          }}
        >
          <div aria-live="polite" className="space-y-2">
            {blockers.map((issue) => (
              <p key={issue.code} className="rounded-xl bg-expense-soft p-3 text-sm text-expense">{issue.message}</p>
            ))}
            {report?.duplicates.map((duplicate) => (
              <div key={duplicate.expense_id} className="rounded-xl bg-caution-soft p-3 text-sm text-caution">
                <p>{duplicate.message}</p>
                <p className="mt-1 font-medium">{duplicate.summary}</p>
              </div>
            ))}
            {warnings.map((issue) => (
              <p key={issue.code} className="rounded-xl bg-caution-soft p-3 text-sm text-caution">{issue.message}</p>
            ))}
          </div>

          {amountInput("total", currency === "USD" ? "Total ($)" : `Total (${currency})`, true)}

          <Field label="Merchant" htmlFor="merchant" {...fieldState("merchant")}>
            <input
              id="merchant"
              maxLength={200}
              autoComplete="off"
              value={values.merchant}
              onChange={(e) => set("merchant", e.target.value)}
              className={`${inputBase} ${fieldState("merchant").status === "check" ? "border-caution" : "border-line"}`}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Date" htmlFor="date" {...fieldState("date")} error={values.date ? undefined : "Choose a date."}>
              <input
                id="date"
                type="date"
                required
                value={values.date}
                onChange={(e) => set("date", e.target.value)}
                className={`${inputBase} ${fieldState("date").status === "check" ? "border-caution" : "border-line"}`}
              />
            </Field>
            <Field label="Category" htmlFor="category" help={report ? `Category from: ${report.category_label}` : undefined}>
              <select
                id="category"
                value={shownCategory}
                onChange={(e) => {
                  setError("");
                  setCategory(e.target.value);
                  setAlwaysUse(false);
                }}
                className={`${inputBase} border-line`}
              >
                {!shownCategory && <option value="" />}
                {categories.map((name) => <option key={name}>{name}</option>)}
              </select>
            </Field>
          </div>

          {report?.category_source === "manual" && values.merchant.trim() && (
            <label className="flex items-start gap-2 text-sm text-pine">
              <input type="checkbox" checked={alwaysUse} onChange={(e) => setAlwaysUse(e.target.checked)} className="mt-0.5 size-4 accent-forest" />
              Always use this category for {values.merchant.trim()}
            </label>
          )}

          <details className="rounded-xl border border-line px-3 py-2.5" open={Boolean(initial.subtotal || initial.tax || initial.tip)}>
            <summary className="cursor-pointer text-sm font-medium text-pine">Subtotal, tax and tip</summary>
            <div className="mt-3 grid grid-cols-3 gap-3 pb-1">
              {amountInput("subtotal", "Subtotal")}
              {amountInput("tax", "Tax")}
              {amountInput("tip", "Tip")}
            </div>
          </details>

          <Field label="Payment method" htmlFor="payment_method">
            <select
              id="payment_method"
              value={values.payment_method}
              onChange={(e) => set("payment_method", e.target.value)}
              className={`${inputBase} border-line`}
            >
              <option value="">Not set</option>
              {PAYMENT_METHODS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </Field>

          <Field label="Note" htmlFor="note">
            <textarea
              id="note"
              rows={2}
              maxLength={1000}
              value={values.note}
              onChange={(e) => set("note", e.target.value)}
              className={`${inputBase} border-line`}
            />
          </Field>

          {rawText && (
            <details className="rounded-xl border border-line px-3 py-2.5">
              <summary className="cursor-pointer text-sm font-medium text-pine">Show extracted text</summary>
              <pre className="mt-3 max-h-64 overflow-auto font-sans text-xs whitespace-pre-wrap text-muted">{rawText}</pre>
            </details>
          )}

          {error && <p role="alert" className="rounded-xl bg-expense-soft p-3 text-sm text-expense">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={!canSave}
              className="flex-1 rounded-xl bg-forest px-4 py-3 font-medium text-white transition-colors hover:bg-pine disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Saving…" : existing ? "Save changes" : "Save expense"}
            </button>
            <button
              type="button"
              onClick={onDiscard}
              className="rounded-xl border border-line px-5 py-3 font-medium text-pine transition-colors hover:bg-mint"
            >
              {existing ? "Cancel" : "Discard"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
