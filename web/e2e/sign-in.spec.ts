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
            user: { id: USER_ID, aud: "authenticated", email: EMAIL, app_metadata: { provider: "email", providers: ["email"] }, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" },
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

test("creating an account sends the name", async ({ page }) => {
  await fakeBackends(page, []);
  let sent: Record<string, string> = {};
  let signUps = 0;
  await page.route("**/fake-supabase/auth/v1/signup**", (route) => {
    signUps += 1;
    sent = route.request().postDataJSON().data;
    return route.fulfill({
      json: { id: USER_ID, aud: "authenticated", email: EMAIL, app_metadata: {}, user_metadata: sent, created_at: "2026-01-01T00:00:00Z" },
    });
  });
  await page.goto(APP);
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("First name").fill("  Sam ");
  await page.getByLabel("Last name").fill("Example");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password", { exact: true }).fill("a-long-password");

  await page.getByLabel("Confirm password").fill("a-different-password");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert")).toContainText("Passwords don't match.");
  await expect(page.getByLabel("Confirm password")).toBeFocused();
  expect(signUps).toBe(0);

  await page.getByLabel("Confirm password").fill("a-long-password");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Check your email")).toBeVisible();
  expect(signUps).toBe(1);
  expect(sent).toEqual({ first_name: "Sam", last_name: "Example" });
});

test("confirming an email leads to the sign-in page, not into the app", async ({ page }) => {
  await fakeBackends(page, []);
  let redirect = "";
  await page.route("**/fake-supabase/auth/v1/signup**", (route) => {
    redirect = new URL(route.request().url()).searchParams.get("redirect_to") ?? "";
    return route.fulfill({
      json: { id: USER_ID, aud: "authenticated", email: EMAIL, app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" },
    });
  });
  await page.goto(APP);
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("First name").fill("Sam");
  await page.getByLabel("Last name").fill("Example");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password", { exact: true }).fill("a-long-password");
  await page.getByLabel("Confirm password").fill("a-long-password");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Check your email")).toBeVisible();
  expect(redirect).toBe(`${new URL(APP).origin}/?confirmed=1`);

  let exchanged = false;
  await page.route("**/fake-supabase/auth/v1/token**", (route) => {
    exchanged = true;
    return route.fulfill({
      json: {
        access_token: TOKEN,
        refresh_token: "made-up-refresh-token",
        token_type: "bearer",
        expires_in: 3600,
        expires_at: Math.floor(Date.now() / 1000) + 3600,
        user: { id: USER_ID, aud: "authenticated", email: EMAIL, app_metadata: { provider: "email", providers: ["email"] }, user_metadata: { first_name: "Sam", last_name: "Example" }, created_at: "2026-01-01T00:00:00Z" },
      },
    });
  });
  await page.goto(`${APP}?confirmed=1&code=made-up-code`);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Your email is confirmed");
  await expect(page).toHaveURL(APP);
  expect(exchanged).toBe(true);

  await page.reload(); // the session from the link really is gone
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByText("Your email is confirmed")).toHaveCount(0);
});

test("an expired confirmation link says so on the sign-in page", async ({ page }) => {
  await fakeBackends(page, []);
  await page.goto(`${APP}?confirmed=1#error=access_denied&error_code=otp_expired`);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("expired or was already used");
  await expect(page).toHaveURL(APP);
});

test("an account without a name is asked once, then shows the name instead of the email", async ({ page }) => {
  await fakeBackends(page, []);
  await page.route("**/fake-supabase/auth/v1/user**", (route) =>
    route.fulfill({
      json: {
        id: USER_ID,
        aud: "authenticated",
        email: EMAIL,
        app_metadata: {},
        user_metadata: route.request().postDataJSON().data,
        created_at: "2026-01-01T00:00:00Z",
      },
    }),
  );
  await page.goto(APP);
  await signIn(page, "right-password");

  await expect(page.getByRole("heading", { name: "What should we call you?" })).toBeVisible();
  await expect(page.getByText(EMAIL).filter({ visible: true })).toBeVisible();

  await page.getByLabel("First name").fill("Sam");
  await page.getByLabel("Last name").fill("Example");
  await page.getByRole("button", { name: "Save name" }).click();

  await expect(page.getByText("Sam Example").filter({ visible: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What should we call you?" })).toHaveCount(0);
  await expect(page.getByText(EMAIL)).toHaveCount(0);
});

test("deleting an account needs the right password, which never goes to our API", async ({ page }) => {
  await fakeBackends(page, []);
  const apiBodies: string[] = [];
  let deleted = false;
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { name: "", monthly_budget: null, cycle_start_day: 1 } }),
  );
  await page.route("**/api/account", (route) => {
    apiBodies.push(route.request().postData() ?? "");
    deleted = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto(APP);
  await signIn(page, "right-password");
  await page.getByRole("link", { name: "Settings" }).filter({ visible: true }).click();

  const remove = page.getByRole("button", { name: "Delete permanently" });
  await expect(page.getByLabel("Type DELETE to confirm")).toHaveCount(0);
  await expect(remove).toBeDisabled();

  await page.getByLabel("Enter your password to confirm").fill("wrong-password");
  await remove.click();
  await expect(page.getByRole("alert")).toContainText("That password isn't right");
  expect(deleted).toBe(false);
  await expect(page.getByLabel("Enter your password to confirm")).toHaveValue("");

  await page.getByLabel("Enter your password to confirm").fill("right-password");
  await remove.click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  expect(deleted).toBe(true);
  expect(apiBodies).toEqual([JSON.stringify({ confirm: "DELETE" })]);
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
