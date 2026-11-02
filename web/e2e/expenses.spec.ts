import { expect, test, type Page } from "@playwright/test";

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function today() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function lastMonth() {
  const now = new Date();
  const day = new Date(now.getFullYear(), now.getMonth() - 1, 10);
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-10`;
}

const unique = (name: string) => `${name} ${test.info().project.name} ${Date.now()}`;
const visible = (page: Page, text: string) => page.getByText(text, { exact: true }).filter({ visible: true });

async function addManually(page: Page, values: { merchant: string; total: string; date?: string; category?: string }) {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter manually instead" }).click();
  await page.getByLabel("Merchant").fill(values.merchant);
  await page.getByLabel(/^Total/).fill(values.total);
  if (values.date) await page.getByLabel("Date").fill(values.date);
  if (values.category) await page.getByLabel("Category").selectOption(values.category);
  await expect(page.getByRole("button", { name: "Save expense" })).toBeEnabled();
  await page.getByRole("button", { name: "Save expense" }).click();
  await expect(page.getByRole("heading", { name: "Expense saved" })).toBeVisible();
}

async function openExpenses(page: Page) {
  await page.getByRole("link", { name: "Expenses", exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole("heading", { name: "Expenses" })).toBeVisible();
}

test("a saved expense appears in the list, and filters narrow it down", async ({ page }) => {
  const recent = unique("Recent Shop");
  const older = unique("Older Shop");
  await addManually(page, { merchant: recent, total: "11.00", date: today(), category: "Education" });
  await addManually(page, { merchant: older, total: "22.00", date: lastMonth(), category: "Health" });
  await openExpenses(page);

  await expect(visible(page, recent)).toBeVisible();
  await expect(visible(page, older)).toHaveCount(0);

  await page.getByLabel("Period").selectOption("all");
  await expect(visible(page, older)).toBeVisible();
  await expect(visible(page, recent)).toBeVisible();

  await page.getByLabel("Category").selectOption("Health");
  await expect(visible(page, older)).toBeVisible();
  await expect(visible(page, recent)).toHaveCount(0);

  await page.reload(); // filters live in the address, so they survive a refresh
  await expect(page.getByLabel("Category")).toHaveValue("Health");
  await expect(visible(page, older)).toBeVisible();
});

test("the total adds up what's shown", async ({ page }) => {
  const category = test.info().project.name === "phone" ? "Travel" : "Entertainment"; // the test database is shared
  await addManually(page, { merchant: unique("Sum One"), total: "10.25", date: today(), category });
  await addManually(page, { merchant: unique("Sum Two"), total: "4.50", date: today(), category });
  await openExpenses(page);
  await page.getByLabel("Category").selectOption(category);
  await expect(page.getByText("$14.75").filter({ visible: true })).toBeVisible();
  await expect(page.getByText("2 expenses")).toBeVisible();
});

test("an expense can be opened, edited, and the list updates", async ({ page }) => {
  const merchant = unique("Edit Shop");
  await addManually(page, { merchant, total: "30.00", date: today() });
  await openExpenses(page);
  await visible(page, merchant).click();

  await expect(page.getByRole("heading", { name: merchant })).toBeVisible();
  await page.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit expense" })).toBeVisible();
  await expect(page.getByLabel(/^Total/)).toHaveValue("30.00");
  await expect(page.getByText("Looks similar")).toHaveCount(0); // not a duplicate of itself

  await page.getByLabel(/^Total/).fill("0");
  await expect(page.getByText("Total must be greater than zero.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();

  await page.getByLabel(/^Total/).fill("31.50");
  await page.getByLabel("Note").fill("Corrected amount");
  await expect(page.getByRole("button", { name: "Save changes" })).toBeEnabled();
  await page.getByRole("button", { name: "Save changes" }).click();

  await expect(page.getByText("$31.50")).toBeVisible();
  await expect(page.getByText("Corrected amount")).toBeVisible();

  await page.getByRole("link", { name: "Back to expenses" }).click();
  await expect(visible(page, merchant)).toBeVisible();
});

test("cancelling an edit changes nothing", async ({ page }) => {
  const merchant = unique("Cancel Shop");
  await addManually(page, { merchant, total: "8.00", date: today() });
  await openExpenses(page);
  await visible(page, merchant).click();
  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByLabel(/^Total/).fill("999");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("$8.00")).toBeVisible();
});

test("deleting asks first, and keeping it changes nothing", async ({ page }) => {
  const merchant = unique("Delete Shop");
  await addManually(page, { merchant, total: "5.00", date: today() });
  await openExpenses(page);
  await visible(page, merchant).click();

  await page.getByRole("button", { name: "Delete" }).click();
  await page.getByRole("button", { name: "Keep it" }).click();
  await expect(page.getByRole("heading", { name: merchant })).toBeVisible();

  const address = page.url();
  await page.getByRole("button", { name: "Delete" }).click();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(page.getByRole("heading", { name: "Expenses" })).toBeVisible();
  await expect(visible(page, merchant)).toHaveCount(0);

  await page.goto(address);
  await expect(page.getByRole("alert")).toContainText("doesn't exist");
});

test("a receipt's extracted text can be viewed after saving", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles({
    name: "default.png",
    mimeType: "image/png",
    buffer: Buffer.from(`text-${test.info().project.name}-${Date.now()}`),
  });
  await expect(page.getByRole("button", { name: "Save expense" })).toBeEnabled();
  await page.getByRole("button", { name: "Save expense" }).click();
  await expect(page.getByRole("heading", { name: "Expense saved" })).toBeVisible();

  await openExpenses(page);
  await page.getByLabel("Period").selectOption("all");
  await visible(page, "Trader Joe").first().click();
  await page.getByText("Show extracted text").click();
  await expect(page.locator("pre").filter({ visible: true })).not.toBeEmpty();
});

test("an empty period explains itself and offers a way out", async ({ page }) => {
  await page.goto("/expenses");
  await page.getByLabel("Category").selectOption("Personal Care");
  await expect(page.getByText("No expenses here yet")).toBeVisible();
  await page.getByRole("button", { name: "Show everything" }).click();
  await expect(page.getByLabel("Category")).toHaveValue("");
  await expect(page.getByLabel("Period")).toHaveValue("all");
});

test("a bad address shows a clear message", async ({ page }) => {
  await page.goto("/expenses/not-a-number");
  await expect(page.getByRole("alert")).toContainText("doesn't exist");
});
