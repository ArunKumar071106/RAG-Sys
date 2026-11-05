import { beforeEach, describe, expect, it } from "vitest";
import { loadScripts } from "./load.js";

let render;
beforeEach(() => {
  render = (text) => {
    const box = document.createElement("div");
    box.append(loadScripts("site-data.js", "markdown.js").markdown.render(text));
    return box;
  };
});

describe("markdown", () => {
  it("renders the tables, lists and labels the answers use", () => {
    const box = render(
      "**Admission – B.E.COURSES** [S1]\n| Department | INTAKE |\n|---|---|\n| CIVIL ENGINEERING | 60 |\n| CSE | 180 |\n\n- Transfer Certificate\n- Mark sheet\n  - 10th\n  - 12th\n\n1. Apply\n2. Pay",
    );
    expect(box.querySelector("p strong").textContent).toBe("Admission – B.E.COURSES");
    expect([...box.querySelectorAll("th")].map((c) => c.textContent)).toEqual(["Department", "INTAKE"]);
    expect([...box.querySelectorAll("tbody tr")].map((r) => r.textContent)).toEqual(["CIVIL ENGINEERING60", "CSE180"]);
    const list = box.querySelector("ul");
    expect(list.children).toHaveLength(2);
    expect([...list.querySelectorAll(":scope ul li")].map((li) => li.textContent)).toEqual(["10th", "12th"]);
    expect([...box.querySelectorAll("ol li")].map((li) => li.textContent)).toEqual(["Apply", "Pay"]);
  });

  it("never turns answer text into HTML or script", () => {
    const box = render('<script>alert(1)</script> <img src=x onerror="alert(2)"> **ok** [x](javascript:alert(3)) ![p](https://e.example/p.png)');
    expect(box.querySelector("script, img, iframe")).toBeNull();
    expect(box.querySelector("a")).toBeNull(); // the javascript: link is text, the image is not shown
    expect(box.textContent).toContain("alert(1)"); // the tags are dropped, the text stays text
    expect(box.querySelector("strong").textContent).toBe("ok");
  });

  it("opens website links in a new tab and marks citations", () => {
    const box = render('See [[2]](https://aaaenggcoll.ac.in/admission/ "Source 2: Admission") and [the form](https://aaaenggcoll.ac.in/admission/online-admission/), or https://aaaenggcoll.ac.in/contact-us/.');
    const [citation, form, bare] = box.querySelectorAll("a");
    expect(citation.className).toBe("citation");
    expect(citation.textContent).toBe("[2]");
    expect(citation.getAttribute("aria-label")).toBe("Source 2: Admission (opens in a new tab)");
    expect(form.getAttribute("target")).toBe("_blank");
    expect(form.getAttribute("rel")).toBe("noopener noreferrer");
    expect(bare.getAttribute("href")).toBe("https://aaaenggcoll.ac.in/contact-us/"); // the full stop is not part of it
  });

  it("keeps a web address inside link text as text, and escaped marks as marks", () => {
    const box = render("[https://aaaenggcoll.ac.in/](https://aaaenggcoll.ac.in/) costs Rs. 5\\*2 file_name_here");
    expect(box.querySelectorAll("a")).toHaveLength(1);
    expect(box.textContent).toContain("5*2 file_name_here");
    expect(box.querySelector("em")).toBeNull();
  });
});
