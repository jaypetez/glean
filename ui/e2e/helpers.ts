import { expect, type Page } from "@playwright/test";

type FixtureName = "default" | "empty";

export async function waitForApi(page: Page): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await page.request.get("/healthz");
        return response.ok();
      },
      { timeout: 10_000 },
    )
    .toBe(true);
}

export async function resetState(page: Page, fixture: FixtureName = "default"): Promise<void> {
  await waitForApi(page);
  const response = await page.request.post(`/api/v1/test/reset?fixture=${fixture}`);
  expect(response.ok()).toBe(true);
  await page.goto("/");
  await page.evaluate(() => localStorage.clear());
}
