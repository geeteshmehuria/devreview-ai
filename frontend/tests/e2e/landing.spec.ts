import { test, expect } from "@playwright/test";

test.describe("Landing page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("renders hero heading", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /AI-Powered/i })).toBeVisible();
  });

  test("renders CTA button linking to login", async ({ page }) => {
    const cta = page.getByRole("link", { name: /Start Reviewing Free/i });
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute("href", "/login");
  });

  test("shows feature cards", async ({ page }) => {
    await expect(page.getByText("AI Code Review")).toBeVisible();
    await expect(page.getByText("Pull Request Analysis")).toBeVisible();
    await expect(page.getByText("Security Scanning")).toBeVisible();
  });

  test("nav bar is visible and sticky", async ({ page }) => {
    const nav = page.locator("nav");
    await expect(nav).toBeVisible();
    await expect(nav).toHaveCSS("position", "fixed");
  });

  test("footer is present", async ({ page }) => {
    const footer = page.locator("footer");
    await expect(footer).toBeVisible();
    await expect(footer).toContainText("DevReview AI");
  });
});

test.describe("Login page", () => {
  test("renders GitHub sign-in button", async ({ page }) => {
    await page.goto("/login");
    const btn = page.getByRole("button", { name: /Continue with GitHub/i });
    await expect(btn).toBeVisible();
  });

  test("shows trust signals", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText(/never store your code/i)).toBeVisible();
  });
});

test.describe("Auth protection", () => {
  test("unauthenticated user is redirected from dashboard to login", async ({ page }) => {
    // Clear any stored tokens
    await page.context().clearCookies();
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });
});
