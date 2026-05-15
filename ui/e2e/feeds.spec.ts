import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("creates, edits, and deletes a feed", async ({ page }) => {
  await page.goto("/feeds/new");
  await expect(page.getByRole("heading", { name: "New feed" })).toBeVisible();

  await page.getByLabel("Name").fill("e2e-crud");
  await page.getByLabel("Schedule").fill("every 2h");
  await page.getByLabel(/Chat ID/).fill("12345");
  await page.locator("#add-source").selectOption("rss");
  await page.getByLabel("url").fill("http://localhost:8080/api/v1/test/rss");
  await page.getByRole("button", { name: "Create feed" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "e2e-crud" })).toBeVisible();

  await page.getByRole("link", { name: "e2e-crud" }).click();
  await expect(page.getByRole("heading", { name: "Edit feed" })).toBeVisible();
  await page.getByLabel("Schedule").fill("daily 10:30");
  await page.getByRole("button", { name: "Save changes" }).click();

  const updatedCard = page.getByRole("listitem").filter({ hasText: "e2e-crud" });
  await expect(updatedCard).toContainText("daily 10:30");

  await page.getByRole("link", { name: "e2e-crud" }).click();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Delete feed e2e-crud");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "e2e-crud" })).toHaveCount(0);
});
