import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("shows defaults, toggles theme, and cancels API key rotation", async ({ page }) => {
  await page.goto("/settings#defaults");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Defaults" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "LLM defaults" })).toBeVisible();
  await expect(page.getByText("qwen2.5:7b")).toBeVisible();
  await expect(page.getByText("Defaults are read-only here for now")).toBeVisible();

  await page.getByRole("tab", { name: "Appearance" }).click();
  await page.getByRole("button", { name: "dark" }).click();
  await expect(page.locator("html")).toHaveClass(/theme-dark/);
  await page.getByRole("button", { name: "light" }).click();
  await expect(page.locator("html")).toHaveClass(/theme-light/);
  await page.getByRole("button", { name: "system" }).click();
  await expect
    .poll(async () => page.evaluate(() => localStorage.getItem("glean.theme")))
    .toBe("system");
  await expect(page.locator("html")).toHaveClass(/theme-(dark|light)/);

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
