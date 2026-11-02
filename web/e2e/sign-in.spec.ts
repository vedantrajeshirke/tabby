import { expect, test, type Page } from "@playwright/test";

// A stand-in for Supabase and the API, with a dev server configured for sign-in mode.
// This proves the screens and token handling. It doesn't replace testing a real project.
const APP = "http://127.0.0.1:5184/";
const USER_ID = "11111111-1111-1111-1111-111111111111";
const EMAIL = "reviewer@example.com";
const TOKEN = "made-up-access-token";

async function fakeBackends(page: Page, seenTokens: (string | undefined)[]) {
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { tesseract_available: true, tesseract_help: null, mock_mode: false, auth_mode: "supabase" } }),
  );
  await page.route("**/api/categories", (route) => {
    seenTokens.push(route.request().headers().authorization);
    return route.fulfill({ json: ["Groceries", "Other"] });
  });
  await page.route("**/fake-supabase/auth/v1/token**", (route) =>
    route.request().postDataJSON().password === "right-password"
      ? route.fulfill({
          json: {
            access_token: TOKEN,
            refresh_token: "made-up-refresh-token",
            token_type: "bearer",
            expires_in: 3600,
            expires_at: Math.floor(Date.now() / 1000) + 3600,
            user: { id: USER_ID, aud: "authenticated", email: EMAIL, app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" },
          },
        })
      : route.fulfill({ status: 400, json: { error_code: "invalid_credentials", msg: "Invalid login credentials" } }),
  );
  await page.route("**/fake-supabase/auth/v1/logout**", (route) => route.fulfill({ status: 204 }));
}

async function signIn(page: Page, password: string) {
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("the app stays closed until sign-in, sends the token, and sign-out clears the screens", async ({ page }) => {
  const seenTokens: (string | undefined)[] = [];
  await fakeBackends(page, seenTokens);
  await page.goto(APP);

  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByText("Enter manually instead")).toHaveCount(0);
  expect(seenTokens).toHaveLength(0);

  await signIn(page, "wrong-password");
  await expect(page.getByRole("alert")).toContainText("don't match");

  await signIn(page, "right-password");
  await expect(page.getByRole("button", { name: "Enter manually instead" })).toBeVisible();
  await expect(page.getByText("stay in your private account")).toBeVisible();
  await expect.poll(() => seenTokens[0]).toBe(`Bearer ${TOKEN}`);

  await page.getByRole("button", { name: "Enter manually instead" }).click();
  await page.getByLabel("Merchant").fill("Unsaved Cafe");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  expect(page.url()).not.toContain(TOKEN);

  await signIn(page, "right-password");
  await expect(page.getByRole("button", { name: "Enter manually instead" })).toBeVisible();
  await expect(page.getByText("Unsaved Cafe")).toHaveCount(0);
});

test("create-account and reset screens are reachable", async ({ page }) => {
  await fakeBackends(page, []);
  await page.goto(APP);
  await page.getByRole("button", { name: "Create an account" }).click();
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await page.getByRole("button", { name: "Back to sign in" }).click();
  await page.getByRole("button", { name: "Forgot password?" }).click();
  await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();
});
