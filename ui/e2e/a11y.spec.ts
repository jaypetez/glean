import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { resetState } from "./helpers";

const routes: Array<{ path: string; heading: string; fixture?: "default" | "empty" }> = [
  { path: "/", heading: "Feeds" },
  { path: "/feeds/new", heading: "New feed" },
  { path: "/skills", heading: "Skills" },
  { path: "/setup", heading: "Create your first glean feed", fixture: "empty" },
  { path: "/settings", heading: "Settings" },
];

async function scanRoute(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const seriousOrCritical = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  const lowerImpact = results.violations.filter(
    (violation) => violation.impact !== "serious" && violation.impact !== "critical",
  );
  if (lowerImpact.length > 0) {
    console.warn(
      `axe lower-impact violations: ${lowerImpact
        .map((violation) => `${violation.id}:${violation.impact ?? "unknown"}`)
        .join(", ")}`,
    );
  }
  expect(seriousOrCritical).toEqual([]);
}

for (const route of routes) {
  test(`has no serious or critical axe violations on ${route.path}`, async ({ page }) => {
    await resetState(page, route.fixture ?? "default");
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
    await scanRoute(page);
  });
}
