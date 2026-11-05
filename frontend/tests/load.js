// Loads the real page into the test browser (jsdom): index.html's body, then the scripts in the
// order index.html lists them, as a browser would.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(ROOT, "index.html"), "utf8");
const scripts = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => m[1]);

export function jsonResponse(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

/** A fresh page; fetch answers /api/health with ok unless the test's fetch says otherwise. */
export function loadPage(fetchImpl) {
  delete window.Arivazhai;
  document.body.innerHTML = html.slice(html.indexOf("<body>") + 6, html.indexOf("</body>")).replace(/<script[\s\S]*?<\/script>/g, "");
  window.fetch = (url, init) => (String(url).includes("/api/health") ? Promise.resolve(jsonResponse({ status: "ok" })) : fetchImpl ? fetchImpl(url, init) : new Promise(() => {}));
  for (const src of scripts) window.eval(readFileSync(join(ROOT, src), "utf8"));
  return window.Arivazhai;
}

export function loadScripts(...names) {
  delete window.Arivazhai;
  for (const src of scripts) if (names.some((n) => src.endsWith(n))) window.eval(readFileSync(join(ROOT, src), "utf8"));
  return window.Arivazhai;
}

export const flush = () => new Promise((r) => setTimeout(r, 0));

export function deferred() {
  let resolve;
  const promise = new Promise((r) => (resolve = r));
  return { promise, resolve };
}

export const answerResult = {
  answer: "Admission is through **TNEA counselling** [S1]. The fee table is on the admissions page [S2]. See the notice [I1].",
  mode: "llm",
  insufficient_evidence: false,
  sources: [
    { id: "S1", chunk_id: "c1", title: "Admissions", url: "https://aaaenggcoll.ac.in/admission", heading: "Admission Process", snippet: "Admission to B.E. programmes is through TNEA counselling.", score: 0.03 },
    { id: "S2", chunk_id: "c2", title: "Fee Structure", url: "https://aaaenggcoll.ac.in/fees", heading: "", snippet: "Tuition fee per year.", score: 0.02 },
  ],
  related_sources: [],
  images: [
    {
      id: "I1", image_id: "img1", src: "/api/images/img1/file", original_url: "https://aaaenggcoll.ac.in/images/notice.png",
      source_page: "https://aaaenggcoll.ac.in/admission", page_title: "Admissions", heading: "Notice", alt: "Admission notice",
      caption: "Admissions open", ocr_text: "ADMISSIONS OPEN", description: "A poster with a red header.", description_is_ai_generated: true,
      width: 900, height: 1200,
    },
  ],
  notice: "",
  model: "",
  timings_ms: {},
  follow_ups: ["What documents are needed for admission?"],
};

export const noAnswerResult = {
  answer: "I couldn't find this in the official AAACET website content I have access to.",
  mode: "no_answer",
  insufficient_evidence: true,
  sources: [],
  related_sources: [{ ...answerResult.sources[0], id: "R1" }],
  images: [],
  notice: "",
  model: "",
  timings_ms: {},
};
