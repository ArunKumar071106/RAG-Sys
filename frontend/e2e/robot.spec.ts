import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Arivazhai's moments: the robot pops up centred over a blurred screen for 2-4 s and never stays in
// the chat. The chat API is replaced with fixed replies here so each moment is shown on purpose;
// the real backend is exercised in assistant.spec.ts.
const SHOTS = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots", "robot");
mkdirSync(SHOTS, { recursive: true });

const NO_DATA = {
  answer: "I couldn't find this in the official AAACET website content I have access to.",
  mode: "no_answer",
  insufficient_evidence: true,
  sources: [],
  related_sources: [],
  images: [],
  notice: "",
  model: "",
  timings_ms: {},
};

const overlay = (page: Page) => page.locator(".moment");
const robot = (page: Page) => page.locator(".moment svg.rb");

async function shot(page: Page, name: string, desktop: boolean) {
  if (!desktop) return;
  await page.waitForTimeout(400); // fully faded and blurred in
  await page.screenshot({ path: join(SHOTS, `${name}.png`) });
}

async function ask(page: Page, question: string) {
  const box = page.getByLabel("Ask a question about AAACET");
  await box.fill(question);
  await box.press("Enter");
}

async function settled(page: Page) {
  await expect(overlay(page)).not.toHaveClass(/is-shown/, { timeout: 8000 });
}

test("page load: loading, then welcome, then the robot leaves the chat", async ({ page }, info) => {
  const desktop = info.project.name === "desktop";
  await page.route("**/api/health", async (route) => {
    await new Promise((r) => setTimeout(r, 1500)); // a slow first contact, so loading is visible
    await route.continue();
  });
  await page.goto("/");
  await expect(robot(page)).toHaveAttribute("data-moment", "load");
  await expect(overlay(page).getByText("Getting ready…")).toBeVisible();
  await shot(page, "01-loading", desktop);

  await expect(robot(page)).toHaveAttribute("data-moment", "greet", { timeout: 5000 });
  await expect(overlay(page).getByText("Vanakkam! I'm Arivazhai")).toBeVisible();
  await shot(page, "02-welcome", desktop);

  const shownAt = Date.now();
  await settled(page);
  const visibleFor = Date.now() - shownAt;
  expect(visibleFor).toBeLessThan(4000);
  await expect(page.locator(".chat svg.rb")).toHaveCount(0); // never inside the chat
});

test("question sent: thinking over the blurred chat, then the answer", async ({ page }, info) => {
  await page.goto("/");
  await settled(page);
  await ask(page, "What hostel facilities are available?");
  await expect(robot(page)).toHaveAttribute("data-moment", "think");
  await expect(overlay(page).getByText("Finding your answer…")).toBeVisible();
  await shot(page, "03-thinking", info.project.name === "desktop");
  await settled(page);
  await expect(page.getByRole("region", { name: "Sources from the official website" })).toBeVisible({ timeout: 30_000 });
});

test("not on the website: no data", async ({ page }, info) => {
  await page.goto("/");
  await settled(page);
  await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(NO_DATA) }));
  await ask(page, "What is the canteen menu on Friday?");
  await expect(robot(page)).toHaveAttribute("data-moment", "unsure");
  await expect(overlay(page).getByText("I couldn't find that")).toBeVisible();
  await shot(page, "04-no-data", info.project.name === "desktop");
});

test("server failure: error", async ({ page }, info) => {
  await page.goto("/");
  await settled(page);
  await page.route("**/api/chat", (route) => route.fulfill({ status: 500, contentType: "application/json", body: "{}" }));
  await ask(page, "What are the library timings?");
  await expect(robot(page)).toHaveAttribute("data-moment", "error");
  await expect(overlay(page).getByText("Something went wrong")).toBeVisible();
  await shot(page, "05-error", info.project.name === "desktop");
  await settled(page);
  await expect(page.getByRole("alert")).toContainText("Something went wrong on our side");
});

test("device offline: no network", async ({ page, context }, info) => {
  await page.goto("/");
  await settled(page);
  await context.setOffline(true);
  await expect(robot(page)).toHaveAttribute("data-moment", "net");
  await expect(overlay(page).getByText("You're offline")).toBeVisible();
  await shot(page, "06-no-network", info.project.name === "desktop");
  await ask(page, "Last date to apply?");
  await expect(robot(page)).toHaveAttribute("data-moment", "net");
  await context.setOffline(false);
});

test("the moment never blocks the page and Esc dismisses it", async ({ page }) => {
  await page.goto("/");
  await expect(overlay(page)).toHaveClass(/is-shown/);
  await page.getByLabel("Ask a question about AAACET").fill("typed while the robot is showing");
  await expect(page.getByLabel("Ask a question about AAACET")).toHaveValue("typed while the robot is showing");
  await page.keyboard.press("Escape");
  await settled(page);
});
