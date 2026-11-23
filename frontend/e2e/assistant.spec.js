import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { signedIn } from "./helpers.js";

// Runs against the real FastAPI backend indexed with the FICTIONAL demo site
// (scripts/e2e_backend.sh), in extractive mode (no LLM key needed).
const SHOTS = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots");
mkdirSync(SHOTS, { recursive: true });

async function expectNoHorizontalScroll(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

/** Arivazhai's moment (robot over a blurred screen) has floated away. */
async function momentGone(page) {
  await expect(page.locator(".moment")).not.toHaveClass(/is-shown/, { timeout: 8000 });
}

async function ask(page, question) {
  const box = page.getByLabel("Ask a question about AAACET");
  await box.fill(question);
  await box.press("Enter");
}

test.beforeEach(async ({ page, request }) => {
  await signedIn(page, request);
});

test("welcome screen", async ({ page }, info) => {
  await page.goto("/");
  // phones: the chat is the whole screen; the page title stays for screen readers
  if (info.project.name === "mobile") await expect(page.getByRole("heading", { level: 1, name: "Arivazhai" })).toBeAttached();
  else await expect(page.getByRole("heading", { level: 1, name: "Arivazhai" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Arivazhai", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hello, Test Parent" })).toBeVisible();
  await expect(page.getByText(/Vanakkam! I'm Arivazhai, the AAACET admission assistant/)).toBeVisible();
  await expect(page.getByRole("button", { name: "How do I apply for admission online?" })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await momentGone(page);
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
  expect(await img.evaluate((el) => el.naturalWidth)).toBeGreaterThan(0);
  await poster.getByText("Text in image (OCR)").click();
  await expect(poster.getByText(/ADMISSIONS/i)).toBeVisible();

  await expectNoHorizontalScroll(page);
  await momentGone(page);
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
  await momentGone(page);
  await page.screenshot({ path: join(SHOTS, `${info.project.name}-error.png`), fullPage: false });
  await page.unroute("**/api/chat");
  await alert.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText(/8:00 AM to 8:00 PM/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("keyboard only: suggestion chip and new chat", async ({ page }) => {
  await page.goto("/");
  const chip = page.getByRole("button", { name: "Are hostels available for boys and girls?" });
  await chip.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Sources from the official website" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "New chat" }).focus();
  await page.keyboard.press("Enter");
  // it asks first, with the safe choice focused; Tab to "Delete and start new"
  await expect(page.getByRole("button", { name: "Keep this chat" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Delete and start new" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Sources from the official website" })).toHaveCount(0);
  await expect(page.getByLabel("Ask a question about AAACET")).toBeFocused();
});

test("phones: the chat fills the screen and ☰ opens admission help, the map and the college pages", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "the chat-app layout is for phones");
  await page.goto("/");
  await momentGone(page);
  await expect(page.locator(".site-header")).toBeHidden();
  const chat = await page.locator("#assistant").boundingBox();
  expect(chat.height).toBeGreaterThanOrEqual(page.viewportSize().height - 1);
  const panel = page.getByRole("complementary", { name: "Admission help" });
  await expect(panel).toBeHidden();
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(panel).toBeVisible();
  await expect(panel.getByText("Chatting as Test Parent")).toBeVisible();
  await expect(panel.getByRole("link", { name: "Apply for admission" })).toBeVisible();
  await expect(panel.getByRole("navigation", { name: "College website" }).getByRole("link", { name: "Admissions" })).toBeAttached();
  await page.waitForTimeout(300); // the slide-in
  await page.screenshot({ path: join(SHOTS, "mobile-menu.png") });
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(page.getByRole("button", { name: "Menu" })).toBeFocused();
});

test("embed mode renders only the chat panel", async ({ page }) => {
  await page.goto("/?embed=1");
  await expect(page.getByLabel("Ask a question about AAACET")).toBeVisible();
  await expect(page.getByRole("banner")).toHaveCount(0);
  await expectNoHorizontalScroll(page);
});

test("the page does not grow with the conversation", async ({ page }, info) => {
  await page.goto("/");
  await momentGone(page);
  const questions = ["What is the tuition fee for B.Tech Data Science?", "What are the library timings?", "Is there a hostel?"];
  for (const [i, q] of questions.entries()) {
    await ask(page, q);
    await expect(page.locator(".message--user")).toHaveCount(i + 1);
    await expect(page.getByRole("status")).toHaveCount(0, { timeout: 30_000 });
    if (info.project.name === "mobile") {
      // phones: the conversation scrolls inside the screen; the page itself never grows
      expect(await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeLessThanOrEqual(1);
      continue;
    }
    // the page ends with the footer: no empty space below it that grows with the conversation
    const emptyBelow = await page.evaluate(
      () => document.documentElement.scrollHeight - (document.querySelector(".site-footer").getBoundingClientRect().bottom + window.scrollY),
    );
    expect(emptyBelow).toBeLessThanOrEqual(1);
  }
  await expect(page.getByRole("heading", { name: "You can also ask" })).toHaveCount(1); // under the latest answer only
});

test("the question box is in sight as the page opens", async ({ page }) => {
  // it sticks to the bottom of the screen on every size, so the down arrow is not needed
  await page.goto("/");
  await momentGone(page);
  await expect(page.getByLabel("Ask a question about AAACET")).toBeInViewport();
  await expect(page.getByRole("button", { name: "Go to the chat below" })).toBeHidden();
});

test("down arrow shows the chat is below and takes you there", async ({ page }, info) => {
  test.skip(info.project.name === "mobile", "on phones the chat is the whole screen: nothing is below");
  // a short screen (a small laptop, or a phone turned sideways): the chat starts below it
  await page.setViewportSize({ width: page.viewportSize().width, height: 420 });
  await page.goto("/");
  await momentGone(page);
  const arrow = page.getByRole("button", { name: "Go to the chat below" });
  await expect(arrow).toBeVisible();
  await page.screenshot({ path: join(SHOTS, `${info.project.name}-chat-below.png`) });
  await arrow.click();
  await expect(page.getByLabel("Ask a question about AAACET")).toBeFocused();
  await expect(page.getByLabel("Ask a question about AAACET")).toBeInViewport();
  await expect(arrow).toBeHidden();
});

test("admission help and the college map: beside the chat on desktop, below it on smaller screens", async ({ page }, info) => {
  await page.goto("/");
  await momentGone(page);
  // phones: the panel is the ☰ menu, hidden (also from screen readers) until opened
  if (info.project.name === "mobile") await page.getByRole("button", { name: "Menu" }).click();
  const panel = page.getByRole("complementary", { name: "Admission help" });
  await expect(panel).toBeVisible();
  if (info.project.name !== "mobile") {
    const chat = await page.locator("#assistant").boundingBox();
    const box = await panel.boundingBox();
    if (info.project.name === "desktop") expect(box.x).toBeGreaterThan(chat.x + chat.width - 1);
    else expect(box.y).toBeGreaterThan(chat.y + chat.height - 1);
  }
  const map = panel.locator("iframe");
  await expect(map).toHaveAttribute("title", /AAA College of Engineering and Technology/);
  const apply = await panel.getByRole("link", { name: "Apply for admission" }).boundingBox();
  expect((await map.boundingBox()).y).toBeGreaterThan(apply.y); // the map is under the Apply button
  await expect(panel.getByRole("link", { name: "Open in Google Maps" })).toHaveAttribute("href", /google\.com\/maps/);
  await panel.scrollIntoViewIfNeeded();
  await expect(panel.getByText("4680")).toBeVisible();
  await expect(panel.getByRole("link", { name: /Call the admission office/ })).toHaveAttribute("href", "tel:04562251111");
  await expect(panel.getByRole("link", { name: "Apply for admission" })).toHaveAttribute("href", "https://aaaenggcoll.ac.in/admission/");
});

test("a new answer is shown from its first line, the question box still in sight", async ({ page }) => {
  await page.goto("/");
  await momentGone(page);
  await ask(page, "What is the TNEA counselling code?");
  await expect(page.locator(".message--user")).toHaveCount(1);
  await expect(page.getByRole("status")).toHaveCount(0, { timeout: 30_000 });
  const answer = page.locator(".chat__log > .message--assistant").last();
  await expect(answer).not.toHaveText(/Vanakkam/);
  // the smooth scroll settles with the answer's top just under the Arivazhai bar, which stays on screen
  const bar = await page.locator(".chat__header").boundingBox();
  await expect
    .poll(async () => answer.evaluate((node) => Math.round(node.getBoundingClientRect().top)), { timeout: 5000 })
    .toBeLessThanOrEqual(bar.height + 40);
  expect(await answer.evaluate((node) => node.getBoundingClientRect().top)).toBeGreaterThanOrEqual(bar.height - 1);
  await expect(answer).toBeInViewport({ ratio: 0.1 });
  await expect(page.getByLabel("Ask a question about AAACET")).toBeInViewport();
});
