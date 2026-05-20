import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("feed detail defaults to overview and supports deep-linkable tabs", async ({ page }) => {
  await page.goto("/feeds/e2e-news");

  await expect(page.getByRole("heading", { name: "e2e-news", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Digests" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Runs" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Suppressed" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Edit" })).toBeVisible();
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText(["Home", "Feeds", "e2e-news"]);
  await expect(page.getByText("Last success")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Latest digests" })).toBeVisible();
  await expect(page.getByText("Primary digest 1")).toBeVisible();
  await expect(page.getByText("Primary digest 2")).toBeVisible();
  await expect(page.getByText("Primary digest 3")).toBeVisible();

  await page.getByRole("tab", { name: "Digests" }).click();
  await expect(page).toHaveURL(/\/feeds\/e2e-news#digests$/);
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText([
    "Home",
    "Feeds",
    "e2e-news",
    "Digests",
  ]);
  await expect(page.getByRole("heading", { name: "Digests", exact: true })).toBeVisible();
  await expect(page.getByText("e2e-weekly")).toHaveCount(0);
  await expect(page.getByText("Primary digest 1")).toBeVisible();

  await page.getByRole("tab", { name: "Runs" }).click();
  await expect(page).toHaveURL(/\/feeds\/e2e-news#runs$/);
  await expect(page.getByRole("heading", { name: "Recent runs" })).toBeVisible();
  await expect(page.locator("table").getByText("success", { exact: true })).toHaveCount(3);
  await expect(page.locator("table").getByText("skip", { exact: true })).toHaveCount(1);
  await expect(page.locator("table").getByText("failure", { exact: true })).toHaveCount(1);
  await expect(page.getByText("ConnectionError: timeout")).toBeVisible();

  await page.getByRole("tab", { name: "Edit" }).click();
  await expect(page).toHaveURL(/\/feeds\/e2e-news\/edit$/);
  await expect(page.getByText("Editing", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();
});

test("feed detail deep links to runs and legacy edit routes", async ({ page }) => {
  await page.goto("/feeds/e2e-news#runs");
  await expect(page.getByRole("tab", { name: "Runs" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Recent runs" })).toBeVisible();

  await page.goto("/feeds/e2e-news/edit");
  await expect(page.getByRole("tab", { name: "Edit" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("Editing", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();
});

test("feed detail run-now button is clickable", async ({ page }) => {
  await page.goto("/feeds/e2e-news");

  await page.route("**/api/v1/feeds/e2e-news/run", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.continue();
  });
  const runResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/feeds/e2e-news/run") &&
      response.request().method() === "POST",
  );

  const button = page.getByRole("button", { name: "Run now" });
  await expect(button).toBeVisible();
  await button.click();
  await expect(page.getByRole("button", { name: "Running..." })).toBeDisabled();
  expect((await runResponse).ok()).toBe(true);
  await expect(page.getByRole("button", { name: "Run now" })).toBeEnabled();
});
