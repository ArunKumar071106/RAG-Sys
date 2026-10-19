import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import App, { isEmbedMode, isWidgetMode } from "../App";
import { brand } from "../brand";

afterEach(() => window.history.replaceState(null, "", "/"));

describe("App layout", () => {
  it("renders the site header, navigation, breadcrumb, assistant launcher and footer", () => {
    render(<App />);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Virtual Assistant" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 1, name: "Virtual Assistant" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask Arivazhai about admissions" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("dialog", { hidden: true })).not.toBeVisible();
    expect(screen.getByRole("contentinfo")).toHaveTextContent(brand.college_name);
    expect(screen.getByRole("link", { name: "Skip to the assistant" })).toHaveAttribute("href", "#arivazhai-panel");
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

  it("the skip link and the intro button open the assistant", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("link", { name: "Skip to the assistant" }));
    expect(screen.getByRole("dialog", { name: "Arivazhai chat" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Close Arivazhai chat", expanded: true }));
    expect(screen.getByRole("dialog", { hidden: true })).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Ask Arivazhai" }));
    expect(screen.getByRole("dialog", { name: "Arivazhai chat" })).toBeVisible();
  });

  it("widget mode renders only the floating launcher", () => {
    window.history.replaceState(null, "", "/?widget=1");
    expect(isWidgetMode()).toBe(true);
    render(<App />);
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask Arivazhai about admissions" })).toBeInTheDocument();
    expect(document.documentElement).toHaveClass("is-widget-frame");
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
