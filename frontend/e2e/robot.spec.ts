import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Arivazhai reacting to each conversation scenario. The chat API is replaced with fixed replies
// here so every scenario (answer, ambiguous, missing, failure) is shown deterministically; the
// real backend is exercised in assistant.spec.ts.
const SHOTS = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots", "robot");
mkdirSync(SHOTS, { recursive: true });

const source = {
  id: "S1",
  chunk_id: "c1",
  title: "Admissions",
  url: "https://aaaenggcoll.ac.in/admission/",
  heading: "Admission Process",
  snippet: "Admission to B.E. programmes is through TNEA counselling.",
  score: 0.03,
};
const reply = (overrides: Record<string, unknown>) => ({
  answer: "Admission to B.E. and B.Tech is through **TNEA counselling** [S1].",
  mode: "extractive",
  insufficient_evidence: false,
  sources: [source],
  related_sources: [],
  images: [],
  notice: "",
  model: "",
  timings_ms: {},
  ...overrides,
});
const ANSWER = reply({});
const AMBIGUOUS = reply({
  answer: "I couldn't find this in the official AAACET website content I have access to.",
  mode: "no_answer",
  insufficient_evidence: true,
  sources: [],
  related_sources: [{ ...source, id: "R1" }],
});
const MISSING = reply({ ...AMBIGUOUS, related_sources: [] });

const robot = (page: Page) => page.locator("svg.rb");

async function fresh(page: Page) {
  // a returning visitor: no first-visit greeting or attention wave during the scenario
  await page.addInitScript(() => {
    try {
      localStorage.setItem("arivazhai:greeted", "1");
      sessionStorage.setItem("arivazhai:nudged", "1");
    } catch {
      /* storage blocked */
    }
  });
  await page.goto("/");
}

function replyWith(page: Page, body: unknown, delayMs = 0) {
  return page.route("**/api/chat", async (route: Route) => {
    if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function shot(page: Page, name: string, isDesktop: boolean) {
  if (!isDesktop) return;
  await page.waitForTimeout(300); // let the panel finish its opening fade
  await page.screenshot({ path: join(SHOTS, `${name}.png`) });
}

async function open(page: Page) {
  await page.getByRole("button", { name: "Ask Arivazhai about admissions" }).click();
  await expect(page.getByRole("dialog", { name: "Arivazhai chat" })).toBeVisible();
}

async function send(page: Page, question: string) {
  const box = page.getByLabel("Ask a question about AAACET");
  await box.fill(question);
  await box.press("Enter");
}

test("launcher: idle, reaching toward the chat, greeting when opened", async ({ page }, info) => {
  const desktop = info.project.name === "desktop";
  await fresh(page);
  const launcher = page.getByRole("button", { name: "Ask Arivazhai about admissions" });
  await expect(launcher).toBeVisible();
  if (info.project.name === "mobile") {
    // head-only disc below 96 px, as the design requires
    await expect(launcher.locator("svg.ic")).toBeVisible();
    await expect(robot(page)).toHaveCount(0);
  } else {
    await expect(robot(page)).toHaveAttribute("data-state", "idle");
    await shot(page, "01-idle-launcher", desktop);
    await launcher.hover();
    await expect(robot(page)).toHaveAttribute("data-state", "support");
    await expect(page.locator(".widget__bubble")).toHaveText("Ask Arivazhai about admissions");
    await shot(page, "02-support-launcher-hover", desktop);
  }
  await launcher.click();
  await expect(robot(page)).toHaveCount(1); // the same single robot, now in the panel
  await expect(robot(page)).toHaveAttribute("data-state", "greet");
  await shot(page, "03-greet-chat-opened", desktop);
});

test("conversation: listening, thinking during retrieval, answer, confirmed action", async ({ page, context }, info) => {
  const desktop = info.project.name === "desktop";
  await fresh(page);
  await replyWith(page, ANSWER, 1500);
  await context.route("https://aaaenggcoll.ac.in/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<title>Admissions</title>" }));
  await open(page);

  await page.getByLabel("Ask a question about AAACET").pressSequentially("How do I apply", { delay: 30 });
  await expect(robot(page)).toHaveAttribute("data-state", "attend");
  await expect(page.locator(".chat__status")).toHaveText("Listening…");
  await shot(page, "04-attend-typing", desktop);

  await page.getByLabel("Ask a question about AAACET").press("Enter");
  await expect(robot(page)).toHaveAttribute("data-state", "think");
  await expect(page.locator(".chat__status")).toHaveText("Searching the official website…");
  await shot(page, "05-think-retrieving", desktop);

  await expect(page.locator(".markdown").getByText("TNEA counselling")).toBeVisible();
  await expect(robot(page)).toHaveAttribute("data-state", "answer");
  await shot(page, "06-answer-ready", desktop);
  await expect(robot(page)).toHaveAttribute("data-state", "idle", { timeout: 5000 }); // after one cycle

  const popup = context.waitForEvent("page");
  await page.getByRole("link", { name: /Source 1: Admissions/ }).click();
  await (await popup).close();
  await expect(robot(page)).toHaveAttribute("data-state", "confirm");
  await expect(page.locator(".chat__status")).toHaveText("Opened the official page");
  await shot(page, "07-confirm-source-opened", desktop);
});

test("ambiguous question: unsure", async ({ page }, info) => {
  await fresh(page);
  await replyWith(page, AMBIGUOUS);
  await open(page);
  await send(page, "what about it");
  await expect(page.getByText(/These official pages may be related/)).toBeVisible();
  await expect(robot(page)).toHaveAttribute("data-state", "unsure");
  await shot(page, "08-unsure-ambiguous", info.project.name === "desktop");
});

test("missing information: error, honestly", async ({ page }, info) => {
  await fresh(page);
  await replyWith(page, MISSING);
  await open(page);
  await send(page, "What is the canteen menu on Friday?");
  await expect(page.getByText(/couldn't find this in the official AAACET website/)).toBeVisible();
  await expect(robot(page)).toHaveAttribute("data-state", "error");
  await expect(page.locator(".chat__status")).toHaveText("That isn't on the official website");
  await shot(page, "09-error-not-in-knowledge-base", info.project.name === "desktop");
});

test("technical failure: error, then back to listening when the visitor types", async ({ page }, info) => {
  await fresh(page);
  await page.route("**/api/chat", (route) => route.abort("internetdisconnected"));
  await open(page);
  await send(page, "What are the library timings?");
  await expect(page.getByRole("alert")).toContainText("Can't reach the assistant");
  await expect(robot(page)).toHaveAttribute("data-state", "error");
  await expect(page.locator(".chat__status")).toHaveText("I can't reach the server right now");
  await shot(page, "10-error-network", info.project.name === "desktop");
  await page.getByLabel("Ask a question about AAACET").pressSequentially("lib", { delay: 30 });
  await expect(robot(page)).toHaveAttribute("data-state", "attend");
});

test("first visit: greeting two seconds after load", async ({ page }) => {
  await page.goto("/");
  test.skip((await page.viewportSize())!.width < 640, "the narrow launcher is the head-only icon");
  await expect(robot(page)).toHaveAttribute("data-state", "greet", { timeout: 4000 });
  await expect(page.locator(".widget__bubble")).toHaveText("Hi! I'm Arivazhai");
});

test("college website: one script tag adds the floating assistant", async ({ page, baseURL }, info) => {
  // a stand-in college page (served on the app's origin; this sandbox's browser cannot reach a second local port)
  const host = `${baseURL}/college-demo.html`;
  await page.route(host, (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html><head><title>AAACET</title></head><body style="margin:0;font-family:sans-serif">
        <h1 style="padding:24px">AAA College of Engineering and Technology</h1>
        <script src="${baseURL}/arivazhai-widget.js" defer></script></body></html>`,
    }),
  );
  await page.goto(host);
  const frameEl = page.locator('iframe[title="Arivazhai admission assistant"]');
  await expect(frameEl).toBeVisible();
  const frame = page.frameLocator('iframe[title="Arivazhai admission assistant"]');
  const closed = (await frameEl.boundingBox())!;
  expect(closed.width).toBeLessThan(400);
  await frame.getByRole("button", { name: "Ask Arivazhai about admissions" }).click();
  await expect(frame.getByRole("dialog", { name: "Arivazhai chat" })).toBeVisible();
  await expect.poll(async () => (await frameEl.boundingBox())!.height).toBeGreaterThan(closed.height + 200);
  await expect(frame.locator("svg.rb")).toHaveAttribute("data-state", "greet");
  if (info.project.name === "desktop") await page.screenshot({ path: join(SHOTS, "11-college-website-widget.png") });
  await frame.getByRole("button", { name: "Close Arivazhai chat" }).first().click();
  await expect.poll(async () => (await frameEl.boundingBox())!.height).toBeLessThan(200);
});
