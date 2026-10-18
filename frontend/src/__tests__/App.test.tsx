import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import App, { isEmbedMode } from "../App";
import { brand } from "../brand";

afterEach(() => window.history.replaceState(null, "", "/"));

describe("App layout", () => {
  it("renders the site header, navigation, breadcrumb, chat and footer", () => {
    render(<App />);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Virtual Assistant" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 1, name: "Virtual Assistant" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: `${brand.short_name} Virtual Assistant` })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent(brand.college_name);
    expect(screen.getByRole("link", { name: "Skip to the question box" })).toHaveAttribute("href", "#chat-message");
  });

  it("mobile menu toggle exposes its state", async () => {
    const user = userEvent.setup();
    render(<App />);
    const toggle = screen.getByRole("button", { name: "Open menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
  });

  it("embed mode renders only the chat panel", () => {
    window.history.replaceState(null, "", "/?embed=1");
    expect(isEmbedMode()).toBe(true);
    render(<App />);
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ask a question about AAACET")).toBeInTheDocument();
  });
});
