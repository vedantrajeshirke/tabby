import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { ApiError, getCategories, getPeriods, LIST_LIMIT, listExpenses, type Period, type SavedExpense } from "../api";
import { formatDate, formatMoney, localToday, paymentLabel } from "../format";

const ALL_TIME = "all";
const selectClass = "mt-1 w-full rounded-xl border border-line bg-white px-3 py-2.5 text-base focus:border-forest";

function periodKey(period: Period) {
  return `${period.start}_${period.end}`;
}

export function CategoryTag({ name }: { name: string }) {
  return <span className="inline-block rounded-full bg-mint px-2.5 py-0.5 text-xs font-medium whitespace-nowrap text-pine">{name}</span>;
}

export function SyntheticTag() {
  return <span className="inline-block rounded-full border border-line px-2 py-0.5 text-xs font-medium text-muted">Synthetic</span>;
}

export default function Expenses() {
  const [params, setParams] = useSearchParams();
  const { search } = useLocation();
  const navigate = useNavigate();
  const [periods, setPeriods] = useState<Period[] | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [expenses, setExpenses] = useState<SavedExpense[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  const requested = params.get("period");
  const selected = periods?.find((p) => periodKey(p) === requested) ?? periods?.[0];
  const allTime = requested === ALL_TIME;
  const period = allTime ? undefined : selected;
  const category = params.get("category") ?? "";

  useEffect(() => {
    Promise.all([getPeriods(localToday()), getCategories()])
      .then(([foundPeriods, foundCategories]) => {
        setPeriods(foundPeriods);
        setCategories(foundCategories);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load your expenses. Please try again."));
  }, [attempt]);

  useEffect(() => {
    if (!periods) return;
    const controller = new AbortController();
    setExpenses(null);
    setError("");
    listExpenses({ start: period?.start, end: period?.end, category }, controller.signal)
      .then(setExpenses)
      .catch((e) => {
        if (controller.signal.aborted) return;
        setError(e instanceof ApiError ? e.message : "Couldn't load your expenses. Please try again.");
      });
    return () => controller.abort();
  }, [periods, period?.start, period?.end, category, attempt]);

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  function open(id: number) {
    navigate(`/expenses/${id}`, { state: { from: search } });
  }

  return (
    <section>
      <h1 className="text-3xl font-semibold tracking-tight text-pine">Expenses</h1>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <label className="text-sm font-medium text-pine">
          Period
          <select
            value={allTime ? ALL_TIME : selected ? periodKey(selected) : ""}
            disabled={!periods}
            onChange={(e) => setFilter("period", e.target.value)}
            className={selectClass}
          >
            {periods?.map((p) => <option key={periodKey(p)} value={periodKey(p)}>{p.label}</option>)}
            <option value={ALL_TIME}>All time</option>
          </select>
        </label>
        <label className="text-sm font-medium text-pine">
          Category
          <select value={category} onChange={(e) => setFilter("category", e.target.value)} className={selectClass}>
            <option value="">All categories</option>
            {categories.map((name) => <option key={name}>{name}</option>)}
          </select>
        </label>
      </div>

      {error && (
        <div role="alert" className="mt-6 rounded-xl bg-expense-soft p-4 text-sm text-expense">
          <p>{error}</p>
          <button onClick={() => { setError(""); setAttempt((n) => n + 1); }} className="mt-2 font-medium underline">Try again</button>
        </div>
      )}

      {!error && !expenses && <p role="status" className="mt-8 text-muted">Loading your expenses…</p>}

      {!error && expenses?.length === 0 && (
        <div className="mt-6 rounded-2xl border border-line p-10 text-center">
          <p className="font-medium text-pine">No expenses here yet</p>
          <p className="mt-1 text-sm text-muted">Try a different period or category, or add a new expense.</p>
          <div className="mt-4 flex flex-wrap justify-center gap-3">
            <Link to="/" className="rounded-xl bg-forest px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-pine">Add expense</Link>
            {(!allTime || category) && (
              <button onClick={() => setParams({ period: ALL_TIME }, { replace: true })} className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-pine transition-colors hover:bg-mint">
                Show everything
              </button>
            )}
          </div>
        </div>
      )}

      {!error && expenses && expenses.length > 0 && (
        <>
          <div className="mt-6 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-line pb-4">
            <p className="amount text-3xl font-semibold">{formatMoney(expenses.reduce((sum, expense) => sum + expense.total, 0))}</p>
            <p className="text-sm text-muted">
              {expenses.length} {expenses.length === 1 ? "expense" : "expenses"}
            </p>
          </div>

          {expenses.length === LIST_LIMIT && (
            <p role="status" className="mt-3 rounded-xl bg-caution-soft p-3 text-sm text-caution">
              Showing the latest {LIST_LIMIT} expenses, so older ones aren't counted in this total. Choose a shorter period to see them.
            </p>
          )}

          <table className="mt-2 hidden w-full text-sm md:table">
            <thead>
              <tr className="text-left text-xs font-medium text-muted">
                <th scope="col" className="py-3 pr-4 font-medium">Date</th>
                <th scope="col" className="py-3 pr-4 font-medium">Merchant</th>
                <th scope="col" className="py-3 pr-4 font-medium">Category</th>
                <th scope="col" className="py-3 pr-4 font-medium">Payment</th>
                <th scope="col" className="py-3 text-right font-medium">Total</th>
              </tr>
            </thead>
            <tbody>
              {expenses.map((expense) => (
                <tr key={expense.id} onClick={() => open(expense.id)} className="cursor-pointer border-t border-line transition-colors hover:bg-mint/30">
                  <td className="py-3.5 pr-4 whitespace-nowrap text-muted">{formatDate(expense.date)}</td>
                  <td className="max-w-64 py-3.5 pr-4">
                    <div className="flex items-center gap-2">
                      <Link to={`/expenses/${expense.id}`} state={{ from: search }} onClick={(e) => e.stopPropagation()} className="truncate font-medium text-pine hover:underline">
                        {expense.merchant}
                      </Link>
                      {expense.is_synthetic && <SyntheticTag />}
                    </div>
                  </td>
                  <td className="py-3.5 pr-4"><CategoryTag name={expense.category} /></td>
                  <td className="py-3.5 pr-4 text-muted">{paymentLabel(expense.payment_method)}</td>
                  <td className="amount py-3.5 text-right font-semibold whitespace-nowrap">{formatMoney(expense.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <ul className="md:hidden">
            {expenses.map((expense) => (
              <li key={expense.id} className="border-b border-line last:border-0">
                <Link to={`/expenses/${expense.id}`} state={{ from: search }} className="flex items-start justify-between gap-4 py-4">
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-pine">{expense.merchant}</span>
                    <span className="mt-0.5 block text-xs text-muted">{formatDate(expense.date)} · {paymentLabel(expense.payment_method)}</span>
                    <span className="mt-2 flex flex-wrap items-center gap-2">
                      <CategoryTag name={expense.category} />
                      {expense.is_synthetic && <SyntheticTag />}
                    </span>
                  </span>
                  <span className="amount shrink-0 font-semibold">{formatMoney(expense.total)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
