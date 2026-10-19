import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ImageCard } from "../components/ImageCard";
import { answerResult } from "../test/fixtures";

const image = answerResult.images[0];

describe("ImageCard", () => {
  it("falls back to the original URL, then to a placeholder", () => {
    render(<ImageCard image={image} index={1} />);
    const img = screen.getByRole("img", { name: "Admission notice" });
    expect(img.getAttribute("src")).toMatch(/\/api\/images\/img1\/file$/);
    fireEvent.error(img);
    expect(screen.getByRole("img", { name: "Admission notice" })).toHaveAttribute("src", image.original_url);
    fireEvent.error(screen.getByRole("img", { name: "Admission notice" }));
    expect(screen.getByRole("img", { name: "Image unavailable: Admission notice" })).toBeInTheDocument();
    expect(screen.getByText("Image unavailable")).toBeInTheDocument();
  });

  it("separates OCR text from AI descriptions", () => {
    render(<ImageCard image={image} index={2} />);
    expect(screen.getByText("Image 2")).toBeInTheDocument();
    expect(screen.getByText("Text in image (OCR)")).toBeInTheDocument();
    expect(screen.getByText("ADMISSIONS OPEN")).toBeInTheDocument();
    expect(screen.getByText("AI-generated description")).toBeInTheDocument();
  });

  it("omits AI label and OCR section when absent and uses a descriptive fallback alt", () => {
    render(<ImageCard image={{ ...image, alt: "", caption: "", ocr_text: "", description: "", description_is_ai_generated: false }} index={1} />);
    expect(screen.getByRole("img", { name: 'Image from the page "Admissions"' })).toBeInTheDocument();
    expect(screen.queryByText("AI-generated description")).not.toBeInTheDocument();
    expect(screen.queryByText("Text in image (OCR)")).not.toBeInTheDocument();
  });

  it("never links to non-http URLs", () => {
    render(<ImageCard image={{ ...image, source_page: "javascript:alert(1)", original_url: "javascript:alert(2)" }} index={1} />);
    expect(screen.queryByRole("link", { name: /View source page/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Open image/ })).not.toBeInTheDocument();
  });

  it("does not repeat the page title in the caption and meta line", () => {
    render(<ImageCard image={{ ...image, alt: "", caption: "", heading: "Hostel Gallery", page_title: "AAA Hostels" }} index={1} />);
    expect(screen.getByText("Hostel Gallery", { selector: ".image-card__title" })).toBeInTheDocument();
    expect(screen.getByText("AAA Hostels", { selector: ".image-card__meta" })).toBeInTheDocument();
  });
});
