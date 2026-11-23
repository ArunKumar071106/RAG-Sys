import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ADMIN_PASSWORD } from "./helpers.js";

// Signing in, the conversation kept on the device, and the admin panel, against the real API on the demo data.
const SHOTS = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots");
mkdirSync(SHOTS, { recursive: true });

async function momentGone(page) {
  await expect(page.locator(".moment")).not.toHaveClass(/is-shown/, { timeout: 8000 });
}

async function ask(page, question) {
  const box = page.getByLabel("Ask a question about AAACET");
  await box.fill(question);
  await box.press("Enter");
  await expect(page.getByRole("status")).toHaveCount(0, { timeout: 30_000 });
  await momentGone(page);
}

test("a visitor signs in with name and number, and the chat comes back after a reload", async ({ page }, info) => {
  await page.goto("/");
  await momentGone(page);
  const box = page.getByLabel("Ask a question about AAACET");
  await expect(box).toBeHidden(); // no chatting before signing in
  await page.getByLabel("Your name").fill("Meena");
  await page.getByLabel("Mobile number").fill("12345");
  await page.getByRole("button", { name: "Start chatting" }).click();
  await expect(page.getByText("Please enter a valid 10-digit mobile number.")).toBeVisible();
  await page.locator("#assistant").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `${info.project.name}-sign-in.png`) });

  await page.getByLabel("Mobile number").fill("91234 56789");
  await page.getByRole("button", { name: "Start chatting" }).click();
  await expect(box).toBeVisible();
  await expect(page.locator(".chat__who")).toContainText("Meena");
  await ask(page, "Is there a hostel?");

  await page.reload();
  await momentGone(page);
  await expect(page.locator(".message--user")).toHaveText(/Is there a hostel\?/);
  // the Arivazhai bar stays on screen while scrolling through the conversation
  await page.mouse.wheel(0, 600);
  await expect(page.locator(".chat__header")).toBeInViewport();

  // New chat warns that the conversation is deleted from this device
  await page.getByRole("button", { name: "New chat" }).click();
  const dialog = page.getByRole("dialog", { name: "Start a new chat?" });
  await expect(dialog).toContainText("deleted from this device");
  await page.screenshot({ path: join(SHOTS, `${info.project.name}-new-chat.png`) });
  await dialog.getByRole("button", { name: "Keep this chat" }).click();
  await expect(page.locator(".message--user")).toHaveCount(1);
  await page.getByRole("button", { name: "New chat" }).click();
  await page.getByRole("button", { name: "Delete and start new" }).click();
  await expect(page.locator(".message--user")).toHaveCount(0);
  await page.reload();
  await momentGone(page);
  await expect(page.locator(".message--user")).toHaveCount(0);
});

test("the admin panel: password, dashboard, answering an unanswered question", async ({ page, request }, info) => {
  test.skip(info.project.name !== "desktop", "one run is enough: it changes the shared demo index");
  const question = "Is there a solar power plant on the campus?";
  // a visitor asks something the website does not answer
  const user = await (await request.post("/api/users", { data: { name: "Ravi", phone: "9876501234" } })).json();
  const before = await (await request.post("/api/chat", { data: { message: question }, headers: { "X-Arivazhai-User": user.token } })).json();
  expect(before.mode).toBe("no_answer");

  await page.goto("/admin.html");
  await page.getByLabel("Password").fill("wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Wrong password.")).toBeVisible();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard", level: 1 })).toBeVisible();
  await expect(page.getByText("Most frequent questions")).toBeVisible();
  await expect(page.locator(".admin-top")).toContainText(question);
  await page.screenshot({ path: join(SHOTS, "admin-dashboard.png"), fullPage: true });

  await page.getByRole("tab", { name: /Unanswered questions/ }).click();
  const row = page.locator(".admin-unanswered > div", { hasText: question });
  await row.getByRole("button", { name: "Answer" }).click();
  await expect(page.getByLabel("Question", { exact: true })).toHaveValue(question);
  await page.getByLabel("Answer", { exact: true }).fill("Yes. A 100 kW solar power plant on the roofs supplies a third of the campus's electricity.");
  await page.getByRole("button", { name: "Save and teach Arivazhai" }).click();
  await expect(page.locator(".admin-toast")).toHaveText("Ready: Arivazhai now uses it.", { timeout: 60_000 });
  await expect(row).toContainText("Answered");

  const after = await (await request.post("/api/chat", { data: { message: "solar power plant on campus" }, headers: { "X-Arivazhai-User": user.token } })).json();
  expect(after.answer).toContain("100 kW");
  expect(after.sources.map((s) => s.url).some((u) => u.startsWith("/api/answers/"))).toBe(true);

  // the visitors' Excel file
  await page.getByRole("tab", { name: "Visitors" }).click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Download Excel/ }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);

  // tidy up: the demo index goes back to how it was
  await page.getByRole("tab", { name: "Your answers" }).click();
  page.once("dialog", (d) => d.accept());
  await page.locator(".admin-answers article", { hasText: question }).getByRole("button", { name: "Delete" }).click();
  // the earlier "Ready" toast may still be showing: ask until the re-indexing has taken the answer out
  await expect
    .poll(async () => (await (await request.post("/api/chat", { data: { message: question }, headers: { "X-Arivazhai-User": user.token } })).json()).mode,
          { timeout: 60_000 })
    .toBe("no_answer");
});

test("admin data is only for the admin", async ({ request }) => {
  for (const path of ["/api/admin/dashboard", "/api/admin/answers", "/api/admin/users.xlsx"]) {
    expect((await request.get(path)).status()).toBe(401);
  }
  expect((await request.post("/api/chat", { data: { message: "hostel" } })).status()).toBe(401);
});

test("the admin uploads a Word file, Arivazhai cites it, and the dashboard can be reset", async ({ page, request }, info) => {
  test.skip(info.project.name !== "desktop", "one run is enough: it changes the shared demo index");
  const { execFileSync } = await import("node:child_process");
  // a small Word file, made by the backend's tests helper (headings, a paragraph and a table)
  const docx = execFileSync("../.venv/bin/python", ["-c",
    "import sys; sys.path.insert(0, '../backend'); from tests.test_admin_files import docx, para, table;" +
    "sys.stdout.buffer.write(docx(para('Sports quota 2026', 'Heading1'), para('Students with state-level sports certificates get a 10 percent fee waiver under the sports quota.'), table(['Level', 'Waiver'], ['State', '10%'], ['National', '25%'])))"]);
  const path = join(SHOTS, "..", "..", "frontend", "test-results", "Sports quota.docx");
  mkdirSync(dirname(path), { recursive: true });
  (await import("node:fs")).writeFileSync(path, docx);

  await page.goto("/admin.html");
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("tab", { name: "Files" }).click();
  await page.locator(".admin-file-input").setInputFiles(path);
  await expect(page.locator(".admin-toast")).toHaveText("Ready: Arivazhai now uses it.", { timeout: 60_000 });
  const row = page.locator(".admin-files article", { hasText: "Sports quota.docx" });
  await expect(row).toContainText("DOCX");
  await page.screenshot({ path: join(SHOTS, "admin-files.png"), fullPage: true });

  const user = await (await request.post("/api/users", { data: { name: "Kavin", phone: "9876512340" } })).json();
  const asked = await (await request.post("/api/chat", { data: { message: "Is there a fee waiver for sports quota students?" },
                                                         headers: { "X-Arivazhai-User": user.token } })).json();
  expect(asked.answer).toContain("10 percent");
  expect(asked.sources.some((s) => s.url.startsWith("/api/files/"))).toBe(true);

  // tidy up, then reset the dashboard
  page.once("dialog", (d) => d.accept());
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.locator(".admin-toast")).toHaveText("Ready: Arivazhai now uses it.", { timeout: 60_000 });
  await expect(page.locator(".admin-files")).toContainText("No files yet.");
  await page.getByRole("tab", { name: "Dashboard" }).click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Reset dashboard" }).click();
  await expect(page.locator(".admin-toast")).toHaveText("The dashboard starts from zero.");
  await expect(page.locator(".admin-tiles")).toContainText("Questions0");
});
