import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

async function seedDigest(
  page: import("@playwright/test").Page,
  payload: {
    feed_name: string;
    style?: "html" | "markdown_v2" | "plain";
    intro?: string | null;
    body: string;
    item_count?: number;
    trace_id?: string | null;
    sent_at?: string;
  },
): Promise<void> {
  const response = await page.request.post("/api/v1/test/seed-digest", { data: payload });
  expect(response.ok()).toBe(true);
}

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("digests renders empty state when history is empty", async ({ page }) => {
  await resetState(page, "empty");
  await page.goto("/digests");

  await expect(page.getByRole("heading", { name: "Digests", exact: true })).toBeVisible();
  await expect(page.getByText("No digests yet")).toBeVisible();
});

test("digests shows a persisted digest after running a feed", async ({ page }) => {
  await page.goto("/digests");
  await expect(page.getByText("Connected")).toBeVisible();

  const runResponse = await page.request.post("/api/v1/feeds/e2e-news/run");
  expect(runResponse.ok()).toBe(true);
  const runResult = (await runResponse.json()) as { error: string | null; sent: number };
  expect(runResult.error).toBeNull();
  expect(runResult.sent).toBeGreaterThan(0);

  const row = page.getByRole("listitem").filter({ hasText: "e2e-news" });
  await expect(row).toContainText("Playwright E2E item", { timeout: 10_000 });
});

test("digests expands a row to show the full body", async ({ page }) => {
  await seedDigest(page, {
    feed_name: "e2e-news",
    intro: "Digest intro",
    body: "Full digest body for expansion",
    style: "plain",
  });

  await page.goto("/digests");
  await page.getByRole("button", { name: /expand digest/i }).click();

  await expect(page.getByText("Full digest body for expansion")).toBeVisible();
});

test("digests sanitizes HTML before rendering", async ({ page }) => {
  page.on("dialog", async (dialog) => {
    throw new Error(`Unexpected dialog: ${dialog.message()}`);
  });

  await seedDigest(page, {
    feed_name: "e2e-news",
    style: "html",
    intro: "Unsafe digest",
    body: '<img src=x onerror="alert(1)"><script>alert(2)</script><p>safe text</p>',
  });

  await page.goto("/digests");
  const row = page.getByRole("listitem").filter({ hasText: "Unsafe digest" });
  await row.getByRole("button", { name: /expand digest/i }).click();

  await expect(row).toContainText("safe text");
  await expect(row.locator("script")).toHaveCount(0);
  await expect(row.locator("img[onerror]")).toHaveCount(0);
});

test("digests preserves live updates that arrive during the initial load", async ({ page }) => {
  let releaseInitialList: (() => void) | null = null;
  const holdInitialList = new Promise<void>((resolve) => {
    releaseInitialList = resolve;
  });
  let intercepted = false;

  await page.route("**/api/v1/digests?limit=50", async (route) => {
    if (intercepted) {
      await route.continue();
      return;
    }
    intercepted = true;
    const response = await route.fetch();
    const body = await response.body();
    await holdInitialList;
    await route.fulfill({ response, body });
  });

  await page.goto("/digests");
  await expect(page.getByText("Connected")).toBeVisible();

  await seedDigest(page, {
    feed_name: "e2e-news",
    intro: "Raced digest",
    body: "Raced body",
    style: "plain",
  });

  releaseInitialList?.();
  await expect(page.getByText("Loading digest history...")).toHaveCount(0);

  const row = page.getByRole("listitem").filter({ hasText: "Raced digest" });
  await expect(row).toBeVisible({ timeout: 10_000 });
});

test("digests keeps queued live updates out of a newly selected feed filter", async ({ page }) => {
  let releaseInitialList: (() => void) | null = null;
  const holdInitialList = new Promise<void>((resolve) => {
    releaseInitialList = resolve;
  });
  let intercepted = false;

  await page.route("**/api/v1/digests?limit=50", async (route) => {
    if (intercepted) {
      await route.continue();
      return;
    }
    intercepted = true;
    const response = await route.fetch();
    const body = await response.body();
    await holdInitialList;
    await route.fulfill({ response, body });
  });

  await page.goto("/digests");
  await expect(page.getByText("Connected")).toBeVisible();

  await seedDigest(page, {
    feed_name: "e2e-news",
    intro: "Queued news digest",
    body: "Queued news body",
    style: "plain",
  });

  await page.evaluate(() => {
    const select = document.querySelector('select[aria-label="Feed filter"]') as HTMLSelectElement | null;
    if (!select) throw new Error("feed filter not found");
    select.value = "e2e-weekly";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });

  releaseInitialList?.();
  await expect(page.getByText("Loading digest history...")).toHaveCount(0);
  await expect(page.getByText("e2e-weekly has not persisted any dashboard digests yet.")).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Queued news digest" })).toHaveCount(0);
});

test("digests keeps the load-more cursor stable after a live prepend", async ({ page }) => {
  const hardReset = await page.request.post("/api/v1/test/reset?fixture=default");
  expect(hardReset.ok()).toBe(true);

  const baseTime = Date.parse("2026-01-01T00:00:00Z");
  for (let i = 1; i <= 27; i += 1) {
    await seedDigest(page, {
      feed_name: "e2e-weekly",
      intro: `Weekly digest [${i}]`,
      body: `Weekly body [${i}]`,
      style: "plain",
      sent_at: new Date(baseTime + (2 * i - 1) * 1_000).toISOString(),
    });
    await seedDigest(page, {
      feed_name: "e2e-news",
      intro: `News digest [${i}]`,
      body: `News body [${i}]`,
      style: "plain",
      sent_at: new Date(baseTime + 2 * i * 1_000).toISOString(),
    });
  }

  await page.goto("/digests");
  await expect(page.getByText("Connected")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more" })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Weekly digest [2]" })).toHaveCount(0);

  await seedDigest(page, {
    feed_name: "e2e-news",
    intro: "Newest live digest",
    body: "Newest live body",
    style: "plain",
    sent_at: new Date(baseTime + 61 * 1_000).toISOString(),
  });
  await expect(page.getByRole("listitem").filter({ hasText: "Newest live digest" })).toBeVisible();

  await page.getByRole("button", { name: "Load more" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Weekly digest [2]" })).toBeVisible();
});

test("digests filters by feed", async ({ page }) => {
  await seedDigest(page, {
    feed_name: "e2e-news",
    intro: "News digest",
    body: "News body",
    style: "plain",
  });
  await seedDigest(page, {
    feed_name: "e2e-weekly",
    intro: "Weekly digest",
    body: "Weekly body",
    style: "plain",
  });

  await page.goto("/digests");
  await page.getByLabel("Feed filter").selectOption("e2e-weekly");

  const weeklyRow = page.getByRole("listitem").filter({ hasText: "e2e-weekly" });
  const newsRow = page.getByRole("listitem").filter({ hasText: "e2e-news" });
  await expect(weeklyRow).toContainText("Weekly digest");
  await expect(newsRow).toHaveCount(0);
});
