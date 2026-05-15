import { expect, test } from "./fixtures";
import { resetState } from "./helpers";

test("redirects to setup and installs a starter template", async ({ page }) => {
  await resetState(page, "empty");

  await page.goto("/");
  await expect(page).toHaveURL(/\/setup$/);
  await expect(page.getByRole("heading", { name: "Create your first glean feed" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Welcome to glean" })).toBeVisible();
  await expect(page.getByRole("img", { name: "glean" })).toBeVisible();

  await page.getByLabel("I’m ready to start").check();
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByRole("heading", { name: "Telegram delivery" })).toBeVisible();
  await page.getByLabel("Bot token").fill("123456:ABCDEF-e2e");
  await page.getByLabel("Chat ID").fill("12345");
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByRole("heading", { name: "Choose an LLM" })).toBeVisible();
  await page.getByRole("button", { name: "Test settings" }).click();
  await expect(page.getByText("LLM settings validated.")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByRole("heading", { name: "Choose starter templates" })).toBeVisible();
  const template = page.locator("article").filter({ hasText: "AI/ML news" });
  await template.getByRole("button", { name: "Select" }).click();
  await page.getByRole("button", { name: "Install templates" }).click();

  await expect(page.getByRole("heading", { name: "You’re all set" })).toBeVisible();
  await page.getByRole("button", { name: "Go to dashboard" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "ai-ml-news" })).toBeVisible();
});
