import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthCard } from "./AuthCard";

vi.mock("./AuthPanel", () => ({ AuthPanel: () => <form aria-label="Sign in form" /> }));

function screenWidth(desktop: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("min-width") ? desktop : false,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("D96: liquid wordmark beside the sign-in form", () => {
  it("desktop shows the wordmark next to the form", async () => {
    screenWidth(true);
    render(<AuthCard mode="sign-in" routing="hash" />);
    expect(await screen.findByRole("img", { name: "abstract." })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Sign in form" })).toBeInTheDocument();
  });

  it("phones keep the form on its own", () => {
    screenWidth(false);
    render(<AuthCard mode="sign-up" routing="path" />);
    expect(screen.queryByRole("region", { name: "Abstract" })).not.toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Sign in form" })).toBeInTheDocument();
  });
});
