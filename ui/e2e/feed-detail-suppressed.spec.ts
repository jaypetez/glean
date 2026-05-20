import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("feed detail deep links to suppressed tab and shows empty state when there are no suppressions", async ({ page }) => {
  const suppressedResponse = await page.request.get("/api/v1/feeds/e2e-news/suppressed");
  expect(suppressedResponse.ok()).toBe(true);
  expect(await suppressedResponse.json()).toEqual([]);

  await page.goto("/feeds/e2e-news#suppressed");

  await expect(page.getByRole("tab", { name: "Suppressed" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page).toHaveURL(/\/feeds\/e2e-news#suppressed$/);
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText([
    "Home",
    "Feeds",
    "e2e-news",
    "Suppressed",
  ]);
  await expect(page.getByRole("heading", { name: "Suppressed by semantic dedup" })).toBeVisible();
  await expect(page.getByText("No suppressions yet for this feed.")).toBeVisible();
  await expect(page.locator("code", { hasText: "semantic_dedup" })).toBeVisible();
  await expect(page.getByRole("link", { name: "docs/concepts/semantic-dedup.md" })).toBeVisible();
});
