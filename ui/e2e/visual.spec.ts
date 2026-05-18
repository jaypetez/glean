import { expect, test } from "./fixtures";
import { DYNAMIC_MASKS } from "./_masks";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("home visual snapshot", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Glean is running/i })).toBeVisible();
  await expect(page).toHaveScreenshot("home.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.05,
    mask: DYNAMIC_MASKS(page),
  });
});

test("feeds list visual snapshot", async ({ page }) => {
  await page.goto("/feeds");
  await expect(page.getByRole("heading", { name: /Feeds/i })).toBeVisible();
  await expect(page).toHaveScreenshot("feeds-list.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.05,
    mask: DYNAMIC_MASKS(page),
  });
});

test("feed detail overview visual snapshot", async ({ page }) => {
  await page.goto("/feeds/e2e-news");
  await expect(page.getByRole("tab", { name: /Overview/i })).toBeVisible();
  await expect(page).toHaveScreenshot("feed-detail-overview.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.05,
    mask: DYNAMIC_MASKS(page),
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

test("settings api auth visual snapshot", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: /Settings/i })).toBeVisible();
  await expect(page).toHaveScreenshot("settings-api-auth.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.05,
  });
});
