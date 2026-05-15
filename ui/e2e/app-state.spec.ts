import { expect, test } from "./fixtures";
import { waitForApi } from "./helpers";

test("shows branded loading state while initialization is pending", async ({ page }) => {
  await waitForApi(page);
  await page.route("**/api/v1/initialize", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.continue();
  });

  await page.goto("/");

  await expect(page.getByText("Loading…")).toBeVisible();
  await expect(page.getByRole("img", { name: "glean" })).toBeVisible();
});

test("shows branded connection error when initialization fails", async ({ page }) => {
  await waitForApi(page);
  await page.route("**/api/v1/initialize", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "offline" }),
    });
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Can't reach glean" })).toBeVisible();
  await expect(page.getByRole("img", { name: "glean" })).toBeVisible();
  await expect(page.getByText("initialize: 503")).toBeVisible();
});
