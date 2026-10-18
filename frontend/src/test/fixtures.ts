import type { ChatResult } from "../api/types";

export const answerResult: ChatResult = {
  answer: "Admission is through **TNEA counselling** [S1]. The fee table is on the admissions page [S2]. See the notice [I1].",
  mode: "llm",
  insufficient_evidence: false,
  sources: [
    {
      id: "S1",
      chunk_id: "c1",
      title: "Admissions",
      url: "https://aaaenggcoll.ac.in/admission",
      heading: "Admission Process",
      snippet: "Admission to B.E. programmes is through TNEA counselling.",
      score: 0.03,
    },
    {
      id: "S2",
      chunk_id: "c2",
      title: "Fee Structure",
      url: "https://aaaenggcoll.ac.in/fees",
      heading: "",
      snippet: "Tuition fee per year.",
      score: 0.02,
    },
  ],
  related_sources: [],
  images: [
    {
      id: "I1",
      image_id: "img1",
      src: "/api/images/img1/file",
      original_url: "https://aaaenggcoll.ac.in/images/notice.png",
      source_page: "https://aaaenggcoll.ac.in/admission",
      page_title: "Admissions",
      heading: "Notice",
      alt: "Admission notice",
      caption: "Admissions open",
      ocr_text: "ADMISSIONS OPEN",
      description: "A poster with a red header.",
      description_is_ai_generated: true,
      width: 900,
      height: 1200,
    },
  ],
  notice: "",
  model: "claude-opus-5-5",
  timings_ms: {},
};

export const noAnswerResult: ChatResult = {
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

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
