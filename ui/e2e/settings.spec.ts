import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("shows defaults, density selector renders in light-only mode, and cancels API key rotation", async ({ page }) => {
  await page.goto("/settings#defaults");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Defaults" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "LLM defaults" })).toBeVisible();
  await expect(page.getByText("qwen2.5:7b")).toBeVisible();
  await expect(page.getByText("Defaults are read-only here for now")).toBeVisible();

  await page.getByRole("tab", { name: "Appearance" }).click();
  // Theme picker has been removed; UI is always rendered in light mode.
  await expect(page.locator("html")).toHaveClass(/theme-light/);
  await expect(page.locator("html")).not.toHaveClass(/theme-dark/);
  await expect(page.getByText("Glean is always rendered in light mode.")).toBeVisible();
  await page.getByRole("button", { name: "compact" }).click();
  await expect(page.locator("html")).toHaveClass(/density-compact/);
  await page.getByRole("button", { name: "comfortable" }).click();
  await expect(page.locator("html")).not.toHaveClass(/density-compact/);

  let rotateRequests = 0;
  await page.route("**/api/v1/auth/rotate", async (route) => {
    rotateRequests += 1;
    await route.abort();
  });
  await page.getByRole("tab", { name: "API & auth" }).click();
  await page.getByRole("button", { name: "Rotate API key" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Rotate API key?" })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  expect(rotateRequests).toBe(0);
});
