import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("persists defaults, toggles theme, and cancels API key rotation", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  await page.getByLabel("Model name").fill("llama3.1:8b");
  await page.getByRole("button", { name: "Save defaults" }).click();
  await expect(page.getByText("Defaults saved.")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Model name")).toHaveValue("llama3.1:8b");

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
  await page.getByRole("tab", { name: "API Key" }).click();
  await page.getByRole("button", { name: "Rotate API key" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Rotate API key?" })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  expect(rotateRequests).toBe(0);
});
