import { expect, test, type Page } from "@playwright/test";

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function today() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

const SAMPLE = {
  period: { start: "2026-11-01", end: "2026-11-30", label: "November 2026", days_elapsed: 14, days_left: 16, length: 30 },
  expense_count: 6,
  other_currency_count: 1,
  any_synthetic: true,
  spent: 620,
  average_daily: 44.29,
  budget: { budget: 500, spent: 620, remaining: -120, over: 120, safe_per_day: 0 },
  insights: [
    { type: "budget_pace", text: "You've spent $620.00 of your $500.00 budget, made up for this test.", score: 620, tone: "warning", data: {} },
    { type: "small_purchases", text: "Purchases under $10 added up to $30.00 across 6 items.", score: 30, tone: "neutral", data: {} },
  ],
  insights_message: null,
  categories: { rows: [{ category: "Groceries", total: 420, share: 0.6774 }, { category: "Transport", total: 200, share: 0.3226 }], includes_synthetic: true },
  comparison: {
    label: "Nov 1–14 vs Oct 1–14",
    rows: [
      { category: "Groceries", current: 420, previous: 300, change: 120, change_ratio: 0.4 },
      { category: "Transport", current: 200, previous: 250, change: -50, change_ratio: -0.2 },
    ],
    includes_synthetic: false,
  },
  trend: {
    points: [
      { label: "Sep", full_label: "September 2026", total: 480, count: 4, in_progress: false },
      { label: "Oct", full_label: "October 2026", total: 550, count: 4, in_progress: false },
      { label: "Nov", full_label: "November 2026", total: 620, count: 6, in_progress: true },
    ],
    includes_synthetic: false,
  },
  top: { rows: [{ id: 1, merchant: "Sample Grocer", date: "2026-11-05", category: "Groceries", total: 420, is_synthetic: true }], includes_synthetic: true },
};

async function goToDashboard(page: Page) {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

test("saved expenses reach the real dashboard", async ({ page, request }) => {
  const day = today();
  const merchant = `Dashboard Shop ${test.info().project.name} ${Date.now()}`;
  for (const total of [9001, 12, 13]) {
    const saved = await request.post("/api/expenses", {
      data: { merchant, date: day, total, client_today: day, category: "Health" },
    });
    expect(saved.status()).toBe(201);
  }
  await goToDashboard(page);
  await expect(page.getByText("Spent this period")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Where it went" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top expenses" })).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(merchant) }).first()).toBeVisible();
  await expect(page.locator("svg[role=img]")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("fewer than three expenses shows a friendly message instead of empty charts", async ({ page }) => {
  await page.route("**/api/dashboard**", (route) => route.fulfill({ json: { ...SAMPLE, expense_count: 2, other_currency_count: 0 } }));
  await goToDashboard(page);
  await expect(page.getByText("Add 1 more expense this period")).toBeVisible();
  await expect(page.getByRole("link", { name: "Add expense" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Where it went" })).toHaveCount(0);
});

test("over budget, insights, comparison and labels all show", async ({ page }) => {
  await page.route("**/api/dashboard**", (route) => route.fulfill({ json: SAMPLE }));
  await goToDashboard(page);
  await expect(page.getByText("$120.00 over budget")).toBeVisible();
  await expect(page.getByText("made up for this test")).toBeVisible();
  await expect(page.getByText("Heads up")).toBeVisible();
  await expect(page.getByText("Nov 1–14 vs Oct 1–14")).toBeVisible();
  await expect(page.getByText("+$120.00 (+40%)")).toBeVisible();
  await expect(page.getByText("−$50.00 (−20%)")).toBeVisible();
  await expect(page.getByText("Includes synthetic demo data")).toHaveCount(2); // only the sections with synthetic rows
  await expect(page.getByText("1 expense in other currencies isn't counted")).toBeVisible();

  await page.locator('rect[aria-label^="October 2026"]').focus();
  await expect(page.getByRole("status").filter({ hasText: "October 2026" })).toContainText("$550.00");

  await page.getByText("View as table").click();
  await expect(page.getByRole("rowheader", { name: "October 2026" })).toBeVisible();
});

test("without a budget it points to Settings", async ({ page }) => {
  await page.route("**/api/dashboard**", (route) => route.fulfill({ json: { ...SAMPLE, budget: null } }));
  await goToDashboard(page);
  await expect(page.getByRole("link", { name: "Set a monthly budget in Settings" })).toBeVisible();
  await expect(page.getByText("Safe to spend per day")).toHaveCount(0);
});

test("the hide-synthetic toggle asks the server to leave those rows out", async ({ page }) => {
  const asked: (string | null)[] = [];
  await page.route("**/api/dashboard**", (route) => {
    asked.push(new URL(route.request().url()).searchParams.get("hide_synthetic"));
    return route.fulfill({ json: SAMPLE });
  });
  await goToDashboard(page);
  await page.getByLabel("Hide synthetic data").check();
  await expect.poll(() => asked.at(-1)).toBe("true");
  await page.getByLabel("Hide synthetic data").uncheck();
  await expect.poll(() => asked.at(-1)).toBe("false");
});

test("the toggle is hidden when there's no synthetic data", async ({ page }) => {
  await page.route("**/api/dashboard**", (route) => route.fulfill({ json: { ...SAMPLE, any_synthetic: false } }));
  await goToDashboard(page);
  await expect(page.getByLabel("Hide synthetic data")).toHaveCount(0);
});

test("the dashboard refreshes after adding an expense", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/dashboard**", (route) => {
    calls += 1;
    return route.fulfill({ json: SAMPLE });
  });
  await goToDashboard(page);
  await page.getByRole("link", { name: "Add", exact: true }).filter({ visible: true }).click();
  const before = calls;
  await page.getByRole("link", { name: "Dashboard" }).filter({ visible: true }).click();
  await expect.poll(() => calls).toBeGreaterThan(before);
});
