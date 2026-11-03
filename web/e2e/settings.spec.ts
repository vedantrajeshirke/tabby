import { expect, test, type Page } from "@playwright/test";

async function open(page: Page) {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Profile and budget" })).toBeVisible();
}

test("settings save, survive a refresh, and reach the dashboard", async ({ page }) => {
  await open(page);
  await page.getByLabel("Name").fill("Sam");
  await page.getByLabel("Monthly budget (USD)").fill("abc");
  await expect(page.getByText("Enter a number, like 800.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save settings" })).toBeDisabled();

  await page.getByLabel("Monthly budget (USD)").fill("2,000");
  await page.getByLabel("Budget cycle starts on day").selectOption("1");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Name")).toHaveValue("Sam");
  await expect(page.getByLabel("Monthly budget (USD)")).toHaveValue("2000.00");
});

test("demo data loads with labels, can be hidden, and is removed cleanly", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Load synthetic demo data" }).click();
  await expect(page.getByText(/Loaded \d+ synthetic expenses/)).toBeVisible();

  await page.getByRole("link", { name: "Dashboard" }).filter({ visible: true }).click();
  await expect(page.getByRole("heading", { name: "Where it went" })).toBeVisible();
  await expect(page.getByText("Includes synthetic demo data").first()).toBeVisible();
  await expect(page.getByLabel("Hide synthetic data")).toBeVisible();

  await page.getByRole("link", { name: "Expenses", exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole("heading", { name: "Expenses", exact: true })).toBeVisible();
  await page.getByLabel("Period").selectOption("all");
  await expect(page.getByText("Synthetic", { exact: true }).filter({ visible: true }).first()).toBeVisible();

  await page.getByRole("link", { name: "Settings" }).filter({ visible: true }).click();
  await page.getByRole("button", { name: "Remove synthetic demo data" }).click();
  await expect(page.getByText(/Removed \d+ synthetic expenses/)).toBeVisible();

  await page.getByRole("link", { name: "Expenses", exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole("heading", { name: "Expenses", exact: true })).toBeVisible();
  await page.getByLabel("Period").selectOption("all");
  await expect(page.getByText("Synthetic", { exact: true }).filter({ visible: true })).toHaveCount(0);
});

test("deleting needs the exact word, then removes everything", async ({ page, request }) => {
  const day = new Date().toLocaleDateString("en-CA");
  const merchant = `Delete Me ${test.info().project.name}`;
  expect((await request.post("/api/expenses", { data: { merchant, date: day, total: 3, client_today: day } })).status()).toBe(201);

  await open(page);
  const remove = page.getByRole("button", { name: "Delete permanently" });
  await expect(remove).toBeDisabled();
  await page.getByLabel("Type DELETE to confirm").fill("delete");
  await expect(remove).toBeDisabled();
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await remove.click();
  await expect(page.getByText("Choose a photo or file")).toBeVisible();

  const left: unknown[] = await (await request.get("/api/expenses")).json();
  expect(left).toEqual([]);
});
