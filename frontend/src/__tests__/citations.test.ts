import { describe, expect, it } from "vitest";
import { linkCitations } from "../components/citations";
import { answerResult } from "../test/fixtures";

describe("linkCitations", () => {
  it("turns source and image markers into links", () => {
    const md = linkCitations(answerResult.answer, answerResult.sources, answerResult.images, "m1");
    expect(md).toContain('[[1]](https://aaaenggcoll.ac.in/admission "Source 1: Admissions")');
    expect(md).toContain("[[2]](https://aaaenggcoll.ac.in/fees");
    expect(md).toContain("[[image 1]](#m1-I1)");
  });

  it("drops markers that point to unknown sources", () => {
    expect(linkCitations("Fact [S9] and [I4].", answerResult.sources, answerResult.images, "m")).toBe("Fact  and .");
  });

  it("escapes quotes in titles", () => {
    const sources = [{ ...answerResult.sources[0], title: 'The "Best" page' }];
    expect(linkCitations("x [S1]", sources, [], "m")).toContain('"Source 1: The \\"Best\\" page"');
  });
});
