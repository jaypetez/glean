import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("dashboard renders feed cards, run-now state, and SSE connection", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Feeds" })).toBeVisible();
  const card = page.getByRole("listitem").filter({ hasText: "e2e-news" });
  await expect(card.getByRole("heading", { name: "e2e-news" })).toBeVisible();
  await expect(card).toContainText("every 1h");
  await expect(page.getByText("Connected")).toBeVisible();

  await page.route("**/api/v1/feeds/e2e-news/run", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.continue();
  });
  const runResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/feeds/e2e-news/run") &&
      response.request().method() === "POST",
  );

  await card.getByRole("button", { name: "Run now" }).click();
  await expect(card.getByText("running", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Running..." })).toBeDisabled();
  expect((await runResponse).ok()).toBe(true);
  await expect(card.getByRole("button", { name: "Run now" })).toBeEnabled();
});

test("dashboard shows branded empty state", async ({ page }) => {
  await resetState(page, "empty");
  await page.evaluate(() => localStorage.setItem("glean.skipped_setup", "1"));

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Feeds", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No feeds yet" })).toBeVisible();
  await expect(page.getByRole("img", { name: "glean" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create your first feed" })).toBeVisible();
});
