import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Runs against the real FastAPI backend indexed with the FICTIONAL demo site
// (scripts/e2e_backend.sh), in extractive mode (no LLM key needed).
const SHOTS = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots");
mkdirSync(SHOTS, { recursive: true });

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

async function ask(page: Page, question: string) {
  const box = page.getByLabel("Ask a question about AAACET");
  await box.fill(question);
  await box.press("Enter");
}

test("welcome screen", async ({ page }, info) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Virtual Assistant" })).toBeVisible();
  await expect(page.getByText(/Welcome! I'm the AAACET Virtual Assistant/)).toBeVisible();
  await expect(page.getByRole("button", { name: "How do I apply for admission?" })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: join(SHOTS, `${info.project.name}-welcome.png`), fullPage: true });
});

test("answer with official sources and a real retrieved image", async ({ page }, info) => {
  await page.goto("/");
  // hold the real request briefly so the loading state is observable deterministically
  await page.route("**/api/chat", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 600));
    await route.continue();
  });
  await ask(page, "Show me the admission notice poster");
  await expect(page.getByRole("status")).toBeVisible();
  const sources = page.getByRole("region", { name: "Sources from the official website" });
  await expect(sources).toBeVisible({ timeout: 30_000 });
  await expect(sources.getByRole("link").first()).toHaveAttribute("href", /\/admissions\.html$/);
  await expect(sources.getByRole("link").first()).toHaveAttribute("target", "_blank");

  const poster = page.getByRole("figure").filter({ hasText: "Text in image (OCR)" }).first();
  await expect(poster).toBeVisible();
  const img = poster.locator("img");
  await expect(img).toHaveJSProperty("complete", true);
  expect(await img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
  await poster.getByText("Text in image (OCR)").click();
  await expect(poster.getByText(/ADMISSIONS/i)).toBeVisible();

  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: join(SHOTS, `${info.project.name}-answer.png`), fullPage: true });
});

test("suggests questions while typing and asks the picked one", async ({ page }) => {
  await page.goto("/");
  const box = page.getByLabel("Ask a question about AAACET");
  await box.pressSequentially("hos", { delay: 20 });
  const list = page.getByRole("listbox", { name: "Suggested questions" });
  await expect(list).toBeVisible();
  await expect(list.getByRole("option").first()).toContainText(/hostel/i);
  await expectNoHorizontalScroll(page);
  await box.press("ArrowDown");
  const picked = (await list.getByRole("option").first().textContent()) ?? "";
  await box.press("Enter");
  await expect(page.locator(".message--user").last()).toHaveText(new RegExp(picked.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  await expect(list).toBeHidden();
});

test("table facts are answered with a clickable citation", async ({ page }) => {
  await page.goto("/");
  await ask(page, "What is the tuition fee for B.Tech Data Science?");
  await expect(page.getByText(/60,000/).first()).toBeVisible({ timeout: 30_000 });
  const citation = page.locator("a.citation").first();
  await expect(citation).toHaveAttribute("href", /\/admissions\.html$/);
});

test("no-answer state", async ({ page }) => {
  await page.goto("/");
  await ask(page, "zzqx wvvy plorp");
  await expect(page.getByText(/couldn't find this in the official AAACET website/)).toBeVisible({ timeout: 30_000 });
});

test("network error and retry", async ({ page }, info) => {
  await page.goto("/");
  await page.route("**/api/chat", (route) => route.abort("internetdisconnected"));
  await ask(page, "What are the library timings?");
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Can't reach the assistant");
  await page.screenshot({ path: join(SHOTS, `${info.project.name}-error.png`), fullPage: false });
  await page.unroute("**/api/chat");
  await alert.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText(/8:00 AM to 8:00 PM/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("keyboard only: suggestion chip and new chat", async ({ page }) => {
  await page.goto("/");
  const chip = page.getByRole("button", { name: "What hostel facilities are available?" });
  await chip.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Sources from the official website" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "New chat" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Sources from the official website" })).toHaveCount(0);
  await expect(page.getByLabel("Ask a question about AAACET")).toBeFocused();
});

test("mobile menu", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "menu toggle only on small screens");
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav).toBeHidden();
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(nav.getByRole("link", { name: "Virtual Assistant" })).toBeVisible();
  await page.screenshot({ path: join(SHOTS, "mobile-menu.png") });
});

test("embed mode renders only the chat panel", async ({ page }) => {
  await page.goto("/?embed=1");
  await expect(page.getByLabel("Ask a question about AAACET")).toBeVisible();
  await expect(page.getByRole("banner")).toHaveCount(0);
  await expectNoHorizontalScroll(page);
});
