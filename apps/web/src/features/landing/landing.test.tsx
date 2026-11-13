import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { seriousViolations } from "@/test/axe";

import { render as renderToHtml } from "./entry-server";
import { LandingPage } from "./LandingPage";

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  sessionStorage.clear();
  fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Landing page (spec 016)", () => {
  it("AC1 to AC4: hero, how it works, features, plans and closing", async () => {
    const { container } = render(<LandingPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Research papers, made clear." })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /The Abstract workspace/ })).toHaveAttribute("width", "1600");
    const steps = screen.getByRole("region", { name: "How it works" });
    expect(within(steps).getAllByRole("listitem")).toHaveLength(3);
    const features = screen.getByRole("region", { name: "Everything a paper needs" });
    expect(within(features).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "Structured summaries",
      "Understand figures",
      "Custom templates",
      "Stay organized",
    ]);
    const plans = screen.getByRole("region", { name: "Free during preview" });
    expect(within(plans).getByText("20 papers a month")).toBeInTheDocument();
    expect(within(plans).getByText(/Pro, with higher limits, is coming soon/)).toBeInTheDocument();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("D94: How it works shows the demo, paused until it is on screen, with a play button", () => {
    render(<LandingPage />);
    const steps = screen.getByRole("region", { name: "How it works" });
    const video = within(steps).getByLabelText(/Demo: a question about the paper/);
    expect(video).toHaveAttribute("poster", "/landing/demo-poster.webp");
    expect(video).toHaveAttribute("preload", "none");
    expect(within(steps).getByRole("button", { name: "Play the demo" })).toBeInTheDocument();
  });

  it("AC5: Get started goes to sign-up, Log in to sign-in, See how it works to the steps; no API calls", () => {
    render(<LandingPage />);
    const header = screen.getByRole("banner");
    expect(within(header).getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/sign-in/");
    expect(within(header).getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/sign-up/");
    expect(screen.getByRole("link", { name: "See how it works" })).toHaveAttribute("href", "#how");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("AC5: a signed-in visitor gets Open your library instead", () => {
    sessionStorage.setItem("abstract.dev-signed-in", "1");
    render(<LandingPage />);
    const header = screen.getByRole("banner");
    expect(within(header).getByRole("link", { name: "Open your library" })).toHaveAttribute("href", "/app/library");
    expect(within(header).queryByRole("link", { name: "Log in" })).toBeNull();
  });

  it("AC7: the prerendered HTML is the same for everyone and has the page's content", () => {
    sessionStorage.setItem("abstract.dev-signed-in", "1"); // ignored while prerendering
    const html = renderToHtml();
    expect(html).toContain("Research papers, made clear.");
    expect(html).toContain('href="/sign-up/"');
    expect(html).not.toContain("Open your library");
    const dashes = [String.fromCharCode(0x2013), String.fromCharCode(0x2014)];
    expect(dashes.some((d) => html.includes(d))).toBe(false); // no en or em dashes in UI text
  });
});
