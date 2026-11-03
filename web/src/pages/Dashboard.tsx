import { useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError, getDashboard, type Dashboard as Data } from "../api";
import { CategorySplit, PeriodComparison, SpendingTrend } from "../components/charts";
import { formatDate, formatMoney, localToday } from "../format";
import { CategoryTag, SyntheticTag } from "./Expenses";

function Card({ title, note, synthetic, children, className = "" }: {
  title: string;
  note?: string;
  synthetic?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`min-w-0 rounded-2xl border border-line p-5 ${className}`}>
      <h2 className="font-semibold tracking-tight text-pine">{title}</h2>
      {note && <p className="mt-0.5 text-xs text-muted">{note}</p>}
      {synthetic && <p className="mt-1 text-xs font-medium text-caution">Includes synthetic demo data</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Stat({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`amount mt-0.5 text-lg font-semibold ${tone}`}>{value}</dd>
    </div>
  );
}

function BudgetPace({ data }: { data: Data }) {
  const { budget, period } = data;
  const dayLabel = `${period.days_left} ${period.days_left === 1 ? "day" : "days"}`;
  const over = budget && budget.over > 0;
  const paceMark = (period.days_elapsed / period.length) * 100;

  return (
    <section className="rounded-2xl border border-line p-5 md:p-6">
      <p className="text-sm text-muted">{period.is_current ? "Spent this period" : `Spent in ${period.label}`}</p>
      <p className="amount mt-1 text-5xl font-semibold">
        {formatMoney(data.spent)}
        {budget && <span className="text-lg font-normal text-muted"> of {formatMoney(budget.budget)}</span>}
      </p>

      {budget ? (
        <>
          {over && <p className="mt-2 font-medium text-expense">{formatMoney(budget.over)} over budget</p>}
          <div
            role="progressbar"
            aria-label="Budget used"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.min(Math.round((budget.spent / budget.budget) * 100), 100)}
            className="relative mt-5 h-2.5 rounded-full bg-line"
          >
            <div
              className={`h-full rounded-full ${over ? "bg-expense" : "bg-ink"}`}
              style={{ width: `${Math.min((budget.spent / budget.budget) * 100, 100)}%` }}
            />
            <span aria-hidden="true" className="absolute -top-1 h-[18px] w-0.5 bg-forest" style={{ left: `${paceMark}%` }} />
          </div>
          <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
            <span aria-hidden="true" className="h-3 w-0.5 bg-forest" /> Where today falls in this period
          </p>
        </>
      ) : (
        period.is_current && <p className="mt-4 rounded-xl bg-mint p-3 text-sm text-pine">
          <Link to="/settings" className="font-medium underline">Set a monthly budget in Settings</Link> to see your pace and a safe daily amount.
        </p>
      )}

      <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-line pt-4 sm:grid-cols-3">
        {budget && <Stat label="Safe to spend per day" value={formatMoney(budget.safe_per_day)} tone={over ? "text-expense" : ""} />}
        <Stat label="Average per day" value={formatMoney(data.average_daily)} />
        {period.is_current ? <Stat label="Left in this period" value={dayLabel} /> : <Stat label="Expenses" value={String(data.expense_count)} />}
      </dl>
    </section>
  );
}

function Insights({ data }: { data: Data }) {
  return (
    <section className="rounded-2xl bg-mint p-5 text-pine">
      <h2 className="font-semibold tracking-tight">Insights</h2>
      {data.insights_message || data.insights.length === 0 ? (
        <p className="mt-2 text-sm">{data.insights_message ?? "Nothing stands out so far this period."}</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {data.insights.map((insight) => (
            <li key={insight.type} className="flex gap-2.5 text-sm">
              {insight.tone === "warning" ? (
                <span className="mt-0.5 shrink-0 self-start rounded-full bg-white whitespace-nowrap px-2 py-0.5 text-xs font-medium text-expense">Heads up</span>
              ) : (
                <span aria-hidden="true" className="mt-1.5 size-2 shrink-0 rounded-full bg-forest" />
              )}
              <span>{insight.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TopExpenses({ rows }: { rows: Data["top"]["rows"] }) {
  return (
    <ol>
      {rows.map((row) => (
        <li key={row.id} className="border-t border-line first:border-0">
          <Link to={`/expenses/${row.id}`} className="flex items-start justify-between gap-3 py-2.5 hover:underline">
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-pine">{row.merchant}</span>
              <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                {formatDate(row.date)} <CategoryTag name={row.category} />
                {row.is_synthetic && <SyntheticTag />}
              </span>
            </span>
            <span className="amount shrink-0 text-sm font-semibold">{formatMoney(row.total)}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [hideSynthetic, setHideSynthetic] = useState(false);
  const [params, setParams] = useSearchParams();
  const requestedPeriod = params.get("period") ?? "";
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    getDashboard(localToday(), hideSynthetic, requestedPeriod, controller.signal)
      .then(setData)
      .catch((e) => {
        if (controller.signal.aborted) return;
        setError(e instanceof ApiError ? e.message : "Couldn't load your dashboard. Please try again.");
      });
    return () => controller.abort();
  }, [hideSynthetic, requestedPeriod, attempt]);

  const heading = (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-3xl font-semibold tracking-tight text-pine">Dashboard</h1>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {data?.any_synthetic && (
          <label className="flex items-center gap-2 text-sm text-pine">
            <input type="checkbox" checked={hideSynthetic} onChange={(e) => setHideSynthetic(e.target.checked)} className="size-4 accent-forest" />
            Hide synthetic data
          </label>
        )}
        {data && (
          <label className="flex items-center gap-2 text-sm font-medium text-pine">
            Period
            <select
              value={data.period.start}
              onChange={(e) => {
                const choice = data.trend.history.find((p) => p.start === e.target.value);
                setParams(choice?.in_progress ? {} : { period: e.target.value }, { replace: true });
              }}
              className="rounded-xl border border-line bg-white px-3 py-2 text-sm font-normal focus:border-forest"
            >
              {!data.trend.history.some((p) => p.start === data.period.start) && <option value={data.period.start}>{data.period.label}</option>}
              {data.trend.history.map((p) => <option key={p.start} value={p.start}>{p.full_label}</option>)}
            </select>
          </label>
        )}
      </div>
    </div>
  );

  if (error) {
    return (
      <section>
        {heading}
        <div role="alert" className="mt-6 rounded-xl bg-expense-soft p-4 text-sm text-expense">
          <p>{error}</p>
          <button onClick={() => setAttempt((n) => n + 1)} className="mt-2 font-medium underline">Try again</button>
        </div>
      </section>
    );
  }
  if (!data) return <section>{heading}<p role="status" className="mt-6 text-muted">Loading your dashboard…</p></section>;

  if (!data.period.is_current && data.expense_count === 0) {
    return (
      <section className="space-y-6">
        {heading}
        <div className="rounded-2xl border border-line p-10 text-center">
          <p className="font-medium text-pine">No expenses in {data.period.label}</p>
          <p className="mt-1 text-sm text-muted">Choose another period above.</p>
        </div>
      </section>
    );
  }

  // Only the current period gets here empty. Its pace and past spending still say something.
  const empty = data.expense_count === 0;
  const hasHistory = data.trend.history.some((p) => p.total > 0);

  return (
    <section className="space-y-4">
      <div className="pb-2">{heading}</div>
      <BudgetPace data={data} />
      {empty ? (
        <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-mint p-5 text-pine">
          <div>
            <h2 className="font-semibold tracking-tight">No expenses yet this period</h2>
            <p className="mt-0.5 text-sm">Add one to see where your money goes.</p>
          </div>
          <Link to="/" className="rounded-xl bg-forest px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-pine">
            Add expense
          </Link>
        </section>
      ) : (
        <>
          {data.period.is_current && <Insights data={data} />}
          <Card title="Where it went" synthetic={data.categories.includes_synthetic}>
            <CategorySplit rows={data.categories.rows} />
          </Card>
          {data.comparison && (
            <Card title="Compared with last period" note={data.comparison.label} synthetic={data.comparison.includes_synthetic}>
              <PeriodComparison comparison={data.comparison} />
            </Card>
          )}
        </>
      )}
      <div className={`grid gap-4 ${empty ? "" : "md:grid-cols-2"}`}>
        {(!empty || hasHistory) && (
          <Card title="Spending over time" note="Last 6 periods" synthetic={data.trend.includes_synthetic}>
            <SpendingTrend points={data.trend.points} history={data.trend.history} />
          </Card>
        )}
        {!empty && (
          <Card title="Top expenses" synthetic={data.top.includes_synthetic}>
            <TopExpenses rows={data.top.rows} />
          </Card>
        )}
      </div>
    </section>
  );
}
