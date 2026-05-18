import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("settings renders the default tab and deep-links between sub-tabs", async ({ page }) => {
  await page.goto("/settings");

  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "API & auth" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByRole("tab", { name: "Defaults" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Appearance" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Health" })).toBeVisible();
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText(["Home", "Settings"]);
  await expect(page.getByRole("heading", { name: "Current API key" })).toBeVisible();

  await page.goto("/settings#defaults");
  await expect(page.getByRole("tab", { name: "Defaults" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "LLM defaults" })).toBeVisible();
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText([
    "Home",
    "Settings",
    "Defaults",
  ]);

  await page.goto("/settings#appearance");
  await expect(page.getByRole("tab", { name: "Appearance" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByRole("heading", { name: "Theme" })).toBeVisible();
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText([
    "Home",
    "Settings",
    "Appearance",
  ]);

  await page.goto("/settings#health");
  await expect(page.getByRole("tab", { name: "Health" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("Daemon health", { exact: true })).toBeVisible();
  await expect(page.locator('[aria-label="Breadcrumb"] li')).toContainText([
    "Home",
    "Settings",
    "Health",
  ]);
});
