import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

test("lists, creates, edits, and deletes skills", async ({ page }) => {
  await page.goto("/skills");
  await expect(page.getByRole("heading", { name: "Skills" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "e2e-summary" })).toBeVisible();

  await page.getByRole("link", { name: "New skill" }).click();
  await page.getByRole("textbox", { name: "Name", exact: true }).fill("e2e-skill");
  await page.getByLabel("Description").fill("Extracts an E2E signal");
  await page.getByLabel(/Prompt template/).fill("Extract from:\nTITLE: {title}\nBODY: {body}");
  await page.getByLabel("Field name").fill("signal");
  await page.getByRole("combobox", { name: /Type/ }).selectOption("str");
  await page.getByRole("button", { name: "Create skill" }).click();

  await expect(page).toHaveURL(/\/skills$/);
  await expect(page.getByRole("heading", { name: "e2e-skill" })).toBeVisible();

  await page.getByRole("link", { name: /e2e-skill/ }).click();
  await expect(page.getByRole("heading", { name: "Edit skill" })).toBeVisible();
  await page.getByLabel("Description").fill("Updated E2E signal extraction");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Updated E2E signal extraction")).toBeVisible();

  await page.getByRole("link", { name: /e2e-skill/ }).click();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Delete skill e2e-skill");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("heading", { name: "e2e-skill" })).toHaveCount(0);
});
