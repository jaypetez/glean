import type { Locator, Page } from "@playwright/test";

export const DYNAMIC_MASKS = (page: Page): Locator[] => [
  page.locator('[aria-live="polite"]'),
  page.locator('[data-testid$="-timestamp"]'),
  page.locator('[data-testid$="-uptime"]'),
  page.locator('[data-testid$="-elapsed"]'),
];
