import { expect, test } from "./fixtures";

test("manifest.json is served and has expected shape", async ({ request }) => {
  const resp = await request.get("/manifest.json");
  expect(resp.ok()).toBe(true);
  const m = await resp.json();
  expect(m.name).toBe("glean");
  expect(m.theme_color).toBe("#0e1730");
  expect(m.display).toBe("standalone");
  expect(m.icons.length).toBeGreaterThanOrEqual(4);
  expect(m.icons.some((i: any) => i.purpose === "maskable")).toBe(true);
});

test("favicon variants are served", async ({ request }) => {
  for (const path of [
    "/favicon.svg",
    "/favicon-32.png",
    "/favicon-16.png",
    "/apple-touch-icon.png",
    "/icon-192.png",
    "/og-card.png",
  ]) {
    const resp = await request.get(path);
    expect(resp.status(), `${path} should be reachable`).toBe(200);
  }
});

test("og meta tags present in index.html", async ({ page }) => {
  await page.goto("/");
  const ogTitle = await page.locator('meta[property="og:title"]').getAttribute("content");
  expect(ogTitle).toBe("glean");
  const themeColor = await page.locator('meta[name="theme-color"]').getAttribute("content");
  expect(themeColor).toBe("#0e1730");
});
