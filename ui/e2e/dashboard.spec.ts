import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("home renders daemon health, recent digests, and quick actions", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Glean is running", exact: true })).toBeVisible();
  await expect(page.getByText("Daemon status from")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent digests" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Quick actions" })).toBeVisible();
  await expect(page.getByText("Primary digest 1")).toBeVisible();
  await expect(page.getByRole("link", { name: "Add a feed" })).toBeVisible();
  await expect(page.getByRole("link", { name: "View digests" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open settings" })).toBeVisible();
});

test("home stays on the landing page when setup is skipped and config is empty", async ({ page }) => {
  await resetState(page, "empty");
  await page.evaluate(() => localStorage.setItem("glean.skipped_setup", "1"));

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Glean is running", exact: true })).toBeVisible();
  await expect(page.getByText("No digests yet")).toBeVisible();
  await expect(page.getByText("Active feeds")).toBeVisible();
});
