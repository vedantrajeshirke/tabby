import { expect, test, type Page } from "@playwright/test";

// Mock mode picks a made-up result by file name. The bytes only need to differ per test,
// so the exact-duplicate check isn't triggered unless a test wants it.
function upload(page: Page, name: string, contents = `${name}-${Date.now()}-${Math.random()}`) {
  return page.locator('input[type="file"]').setInputFiles({
    name,
    mimeType: name.endsWith(".pdf") ? "application/pdf" : "image/png",
    buffer: Buffer.from(contents),
  });
}

async function saveEnabled(page: Page) {
  await expect(page.getByRole("button", { name: "Save expense" })).toBeEnabled();
}

test("a read receipt is prefilled, confirmed and saved", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("MOCK MODE")).toBeVisible();
  await expect(page.getByText("processed and stored only on this device")).toBeVisible();

  await upload(page, "default.png");
  await expect(page.getByRole("heading", { name: "Check the details" })).toBeVisible();
  await expect(page.getByLabel("Merchant")).toHaveValue("Trader Joe");
  await expect(page.getByLabel(/^Total/)).toHaveValue("23.47");
  await expect(page.getByLabel("Category")).toHaveValue("Groceries");
  await expect(page.getByText("Category from: merchant rule")).toBeVisible();

  await saveEnabled(page);
  await page.getByRole("button", { name: "Save expense" }).click();
  await expect(page.getByRole("heading", { name: "Expense saved" })).toBeVisible();
  await expect(page.getByText("$23.47")).toBeVisible();

  await page.getByRole("button", { name: "Add another" }).click();
  await expect(page.getByText("Choose a photo or file")).toBeVisible();
});

test("the same file again gets a duplicate warning, and can still be saved", async ({ page }) => {
  const contents = `same-file-${test.info().project.name}`;
  await page.goto("/");
  await upload(page, "venmo.png", contents);
  await saveEnabled(page);
  await page.getByRole("button", { name: "Save expense" }).click();
  await page.getByRole("button", { name: "Add another" }).click();

  await upload(page, "venmo.png", contents);
  await expect(page.getByText("You already added this file")).toBeVisible();
  await saveEnabled(page);
});

test("a failed read fills nothing and offers a clearer photo or manual entry", async ({ page }) => {
  await page.goto("/");
  await upload(page, "blurry.png");
  await expect(page.getByRole("heading", { name: "We couldn't fill this in" })).toBeVisible();
  await expect(page.getByText("Lay the receipt flat")).toBeVisible();

  await page.getByRole("button", { name: "Enter manually" }).click();
  await expect(page.getByLabel(/^Total/)).toHaveValue("");
  await expect(page.getByLabel("Merchant")).toHaveValue("");
  await expect(page.getByText("Total amount is required.")).toHaveCount(0);
  await expect(page.getByText("Merchant is required.")).toHaveCount(0);

  await page.getByRole("button", { name: "Save expense" }).click();
  await expect(page.getByText("Total amount is required.")).toBeVisible();
  await expect(page.getByLabel(/^Total/)).toBeFocused();
  await expect(page.getByRole("heading", { name: "Enter the details" })).toBeVisible();
});

test("manual entry blocks bad values until they're fixed, and remembers a category choice", async ({ page }) => {
  const merchant = `Made Up Shop ${test.info().project.name}`;
  await page.goto("/");
  await page.getByRole("button", { name: "Enter manually instead" }).click();
  const save = page.getByRole("button", { name: "Save expense" });

  await page.getByLabel(/^Total/).fill("abc");
  await expect(page.getByText("Enter a number, like 12.50.")).toBeVisible();
  await save.click();
  await expect(page.getByRole("heading", { name: "Enter the details" })).toBeVisible();

  await page.getByLabel(/^Total/).fill("0");
  await expect(page.getByText("Total must be greater than zero.")).toBeVisible();
  await save.click();
  await expect(page.getByRole("heading", { name: "Enter the details" })).toBeVisible();

  await page.getByLabel(/^Total/).fill("1,234.50");
  await page.getByLabel("Date").fill("2099-01-01");
  await expect(page.getByText("Date is in the future.")).toBeVisible();
  await save.click();
  await expect(page.getByRole("heading", { name: "Enter the details" })).toBeVisible();
  await expect(page.getByLabel("Date")).toBeFocused();

  await page.getByLabel("Date").fill("2026-10-01");
  await page.getByLabel("Merchant").fill(merchant);
  await page.getByLabel("Category").selectOption("Education");
  await page.getByLabel(`Always use this category for ${merchant}`).check();
  await saveEnabled(page);
  await save.click();
  await expect(page.getByText("$1,234.50")).toBeVisible();

  await page.getByRole("button", { name: "Add another" }).click();
  await page.getByRole("button", { name: "Enter manually instead" }).click();
  await page.getByLabel("Merchant").fill(merchant);
  await expect(page.getByText("Category from: your past choice")).toBeVisible();
  await expect(page.getByLabel("Category")).toHaveValue("Education");
});

test("required fields are marked, and messages only appear once a field is left empty", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter manually instead" }).click();
  await expect(page.getByText("Required", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: "Merchant is required." })).toHaveCount(0);

  await page.getByLabel("Merchant").focus();
  await page.getByLabel("Note").focus();
  await expect(page.getByText("Merchant is required.")).toBeVisible();
  await page.getByLabel("Merchant").fill("Made Up Cafe");
  await expect(page.getByText("Merchant is required.")).toHaveCount(0);

  await page.getByLabel(/^Total/).focus();
  await page.getByLabel("Note").focus();
  await expect(page.getByText("Total amount is required.")).toBeVisible();
  await page.getByLabel(/^Total/).fill("4.00");
  await expect(page.getByText("Total amount is required.")).toHaveCount(0);

  await page.getByLabel("Date").fill("");
  await page.getByLabel("Note").focus();
  await expect(page.getByText("Choose a date.")).toBeVisible();
});

test("an unsupported file gets a clear message and the page keeps working", async ({ page }) => {
  await page.goto("/");
  await upload(page, "notes.txt");
  await expect(page.getByRole("alert")).toContainText("file type isn't supported");
  await expect(page.getByText("Choose a photo or file")).toBeVisible();
});

test("an unsaved expense survives visiting another page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter manually instead" }).click();
  await page.getByLabel("Merchant").fill("Still Here Cafe");
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByRole("link", { name: "Add" }).click();
  await expect(page.getByLabel("Merchant")).toHaveValue("Still Here Cafe");
});

test("sign-in mode without browser settings refuses to open the app", async ({ page }) => {
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { tesseract_available: true, tesseract_help: null, mock_mode: false, auth_mode: "supabase" } }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Sign-in isn't set up");
  await expect(page.getByText("Add expense")).toHaveCount(0);
});

test("no horizontal scrolling on the confirm screen", async ({ page }) => {
  await page.goto("/");
  await upload(page, "mismatch.png");
  await expect(page.getByRole("heading", { name: "Check the details" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("an expense can't be saved without a merchant", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter manually instead" }).click();
  await page.getByLabel(/^Total/).fill("9.50");
  await expect(page.getByRole("button", { name: "Save expense" })).toBeEnabled();
  await page.getByRole("button", { name: "Save expense" }).click();
  await expect(page.getByText("Merchant is required.")).toBeVisible();
  await expect(page.getByLabel("Merchant")).toBeFocused();
  await expect(page.getByRole("heading", { name: "Enter the details" })).toBeVisible();
});
