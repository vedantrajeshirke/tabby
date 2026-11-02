import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { ApiError, deleteExpense, getCategories, getExpense, type ExpenseDetail } from "../api";
import ConfirmForm from "../components/ConfirmForm";
import { formatDate, formatMoney, paymentLabel } from "../format";
import { CategoryTag, SyntheticTag } from "./Expenses";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-6 border-t border-line py-3 text-sm">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 text-right break-words text-pine">{children}</dd>
    </div>
  );
}

export default function ExpenseDetailPage() {
  const { id = "" } = useParams();
  const { state } = useLocation();
  const navigate = useNavigate();
  const backTo = `/expenses${state?.from ?? ""}`;

  const [expense, setExpense] = useState<ExpenseDetail | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setExpense(null);
    getExpense(id, controller.signal)
      .then(setExpense)
      .catch((e) => {
        if (controller.signal.aborted) return;
        const missing = e instanceof ApiError && (e.status === 404 || e.status === 422);
        setError(missing ? "This expense doesn't exist. It may have been deleted." : e instanceof ApiError ? e.message : "Couldn't load this expense.");
      });
    return () => controller.abort();
  }, [id, attempt]);

  useEffect(() => {
    getCategories().then(setCategories).catch(() => {});
  }, []);

  const back = <Link to={backTo} className="text-sm font-medium text-forest hover:underline">← Back to expenses</Link>;

  if (error) {
    return (
      <section>
        {back}
        <p role="alert" className="mt-6 rounded-xl bg-expense-soft p-4 text-sm text-expense">{error}</p>
      </section>
    );
  }
  if (!expense) return <p role="status" className="text-muted">Loading this expense…</p>;

  if (editing) {
    return (
      <ConfirmForm
        existing={expense}
        categories={categories}
        onDiscard={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          setAttempt((n) => n + 1);
        }}
      />
    );
  }

  async function remove() {
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteExpense(expense!.id);
      navigate(backTo, { replace: true });
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : "Couldn't delete this expense. Please try again.");
      setDeleting(false);
    }
  }

  const rawText = expense.extraction?.raw_text;

  return (
    <section className="max-w-xl">
      {back}
      <div className="mt-6 flex items-start justify-between gap-4">
        <h1 className="min-w-0 text-3xl font-semibold tracking-tight break-words text-pine">{expense.merchant}</h1>
        {expense.is_synthetic && <SyntheticTag />}
      </div>
      <p className="amount mt-3 text-4xl font-semibold">{formatMoney(expense.total, expense.currency)}</p>
      <p className="mt-2 text-muted">{formatDate(expense.date)}</p>

      <dl className="mt-6 border-b border-line">
        <Row label="Category"><CategoryTag name={expense.category} /></Row>
        <Row label="Category from">{expense.category_label}</Row>
        <Row label="Payment">{paymentLabel(expense.payment_method)}</Row>
        {expense.subtotal != null && <Row label="Subtotal"><span className="amount">{formatMoney(expense.subtotal, expense.currency)}</span></Row>}
        {expense.tax != null && <Row label="Tax"><span className="amount">{formatMoney(expense.tax, expense.currency)}</span></Row>}
        {expense.tip != null && <Row label="Tip"><span className="amount">{formatMoney(expense.tip, expense.currency)}</span></Row>}
        {expense.note && <Row label="Note">{expense.note}</Row>}
      </dl>

      {rawText && (
        <details className="mt-4 rounded-xl border border-line px-3 py-2.5">
          <summary className="cursor-pointer text-sm font-medium text-pine">Show extracted text</summary>
          <pre className="mt-3 max-h-64 overflow-auto font-sans text-xs whitespace-pre-wrap text-muted">{rawText}</pre>
        </details>
      )}

      {deleteError && <p role="alert" className="mt-4 rounded-xl bg-expense-soft p-3 text-sm text-expense">{deleteError}</p>}

      {confirmingDelete ? (
        <div className="mt-6 rounded-2xl bg-expense-soft p-4">
          <p className="text-sm font-medium text-expense">Delete this expense? This can't be undone.</p>
          <div className="mt-3 flex gap-3">
            <button onClick={remove} disabled={deleting} className="rounded-xl bg-expense px-4 py-2.5 text-sm font-medium text-white disabled:opacity-60">
              {deleting ? "Deleting…" : "Yes, delete"}
            </button>
            <button onClick={() => setConfirmingDelete(false)} disabled={deleting} className="rounded-xl border border-line bg-white px-4 py-2.5 text-sm font-medium text-pine">
              Keep it
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-6 flex gap-3">
          <button onClick={() => setEditing(true)} className="flex-1 rounded-xl bg-forest px-4 py-3 font-medium text-white transition-colors hover:bg-pine">
            Edit
          </button>
          <button onClick={() => setConfirmingDelete(true)} className="rounded-xl border border-line px-5 py-3 font-medium text-expense transition-colors hover:bg-expense-soft">
            Delete
          </button>
        </div>
      )}
    </section>
  );
}
