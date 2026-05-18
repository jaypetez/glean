import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

async function expectBreadcrumbs(
  page: import("@playwright/test").Page,
  labels: string[],
): Promise<void> {
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText(labels);
}

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("home omits breadcrumbs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByLabel("Breadcrumb")).toHaveCount(0);
});

test("feeds list shows home and feeds breadcrumbs", async ({ page }) => {
  await page.goto("/feeds");
  await expectBreadcrumbs(page, ["Home", "Feeds"]);
});

test("feed detail overview shows feed breadcrumbs", async ({ page }) => {
  await page.goto("/feeds/e2e-news");
  await expectBreadcrumbs(page, ["Home", "Feeds", "e2e-news"]);
});

test("feed detail digests deep link adds the active tab breadcrumb", async ({ page }) => {
  await page.goto("/feeds/e2e-news#digests");
  await expectBreadcrumbs(page, ["Home", "Feeds", "e2e-news", "Digests"]);
});

test("settings health deep link shows nested breadcrumbs", async ({ page }) => {
  await page.goto("/settings#health");
  await expectBreadcrumbs(page, ["Home", "Settings", "Health"]);
});
