import { expect, test } from "@playwright/test";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("dashboard visual snapshot", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Feeds" })).toBeVisible();
  await expect(page.getByText("Connected")).toBeVisible();
  await expect(page).toHaveScreenshot("dashboard.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.05,
    mask: [page.locator('[aria-live="polite"]')],
  });
});

test("new feed visual snapshot", async ({ page }) => {
  await page.goto("/feeds/new");
  await expect(page.getByRole("heading", { name: "New feed" })).toBeVisible();
  await expect(page).toHaveScreenshot("feeds-new.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.05,
  });
});

test("settings visual snapshot", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page).toHaveScreenshot("settings.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.05,
  });
});
