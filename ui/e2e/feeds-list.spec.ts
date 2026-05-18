import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("feeds list route renders feed cards instead of falling through to home", async ({ page }) => {
  await page.goto("/feeds");

  await expect(page.getByRole("heading", { name: "Feeds", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Glean is running", exact: true })).toHaveCount(0);

  const card = page.getByRole("listitem").filter({ hasText: "e2e-news" });
  await expect(card.getByRole("heading", { name: "e2e-news" })).toBeVisible();
  await expect(card).toContainText("every 1h");

  await card.getByRole("link", { name: "Open e2e-news" }).click();
  await expect(page).toHaveURL(/\/feeds\/e2e-news$/);
  await expect(page.getByRole("heading", { name: "e2e-news", exact: true })).toBeVisible();
});

test("feeds list add-a-feed button opens the editor", async ({ page }) => {
  await page.goto("/feeds");

  await page.getByRole("link", { name: "Add a feed" }).click();
  await expect(page).toHaveURL(/\/feeds\/new$/);
  await expect(page.getByRole("heading", { name: "New feed", exact: true })).toBeVisible();
});

test("feeds list shows the branded empty state when there are no feeds", async ({ page }) => {
  await resetState(page, "empty");
  await page.goto("/feeds");

  await expect(page.getByRole("heading", { name: "Feeds", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No feeds yet" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create your first feed" })).toBeVisible();
});
