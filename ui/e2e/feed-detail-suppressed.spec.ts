import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("feed detail deep links to suppressed tab and shows empty state when there are no suppressions", async ({ page }) => {
  const suppressedResponse = await page.request.get("/api/v1/feeds/e2e-weekly/suppressed");
  expect(suppressedResponse.ok()).toBe(true);
  expect(await suppressedResponse.json()).toEqual([]);

  await page.goto("/feeds/e2e-weekly#suppressed");

  await expect(page.getByRole("tab", { name: "Suppressed" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page).toHaveURL(/\/feeds\/e2e-weekly#suppressed$/);
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText([
    "Home",
    "Feeds",
    "e2e-weekly",
    "Suppressed",
  ]);
  await expect(page.getByRole("heading", { name: "Suppressed by semantic dedup" })).toBeVisible();
  await expect(page.getByText("No suppressions yet for this feed.")).toBeVisible();
  await expect(page.locator("code", { hasText: "semantic_dedup" })).toBeVisible();
  await expect(page.getByRole("link", { name: "docs/concepts/semantic-dedup.md" })).toBeVisible();
});

test("feed detail suppressed tab renders seeded rows and paginates", async ({ page }) => {
  const suppressedResponse = await page.request.get("/api/v1/feeds/e2e-news/suppressed?limit=50");
  expect(suppressedResponse.ok()).toBe(true);
  const body = (await suppressedResponse.json()) as Array<{ trace_id: string | null }>;
  expect(body).toHaveLength(50);

  await page.goto("/feeds/e2e-news#suppressed");

  await expect(page.getByRole("columnheader", { name: "When" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Suppressed" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Matched" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Similarity" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "trace_id" })).toBeVisible();
  await expect(page.getByRole("link", { name: "OpenAI launches X — HN discussion" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Introducing X" })).toBeVisible();
  await expect(page.getByText("0.95")).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(50);
  await expect(page.getByText("Suppressed duplicate 00")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Load more" })).toBeVisible();

  await page.getByRole("button", { name: "Load more" }).click();

  await expect(page.locator("tbody tr")).toHaveCount(52);
  await expect(page.getByText("Suppressed duplicate 00")).toBeVisible();
  await expect(page.getByText("Suppressed duplicate 01")).toBeVisible();
});
