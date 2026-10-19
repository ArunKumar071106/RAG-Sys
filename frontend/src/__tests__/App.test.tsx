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
    expect(within(nav).getByRole("link", { name: "Arivazhai" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 1, name: "Arivazhai" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Arivazhai" })).toBeInTheDocument();
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

  it("dropdown menus open with the keyboard and close with Escape", async () => {
    const withChildren = brand.nav.find((item) => (item.children ?? []).length > 0);
    if (!withChildren) return; // provisional brand without submenus
    const user = userEvent.setup();
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    const toggle = within(nav).getByRole("button", { name: withChildren.label });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    toggle.focus();
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const first = withChildren.children![0];
    expect(within(nav).getByRole("link", { name: first.label })).toHaveAttribute("href", expect.stringMatching(/^https?:/));
    await user.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("shows the measured header note and buttons", () => {
    render(<App />);
    if (brand.header_note) expect(screen.getAllByText(brand.header_note).length).toBeGreaterThan(0);
    for (const button of brand.header_buttons ?? []) {
      expect(screen.getAllByRole("link", { name: button.label }).length).toBeGreaterThan(0);
    }
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
