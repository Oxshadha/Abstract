import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FieldError } from "./FieldError";
import { StatusPill } from "./StatusPill";

describe("AC5: status components own the semantic colours", () => {
  it("renders success with its token colours and an icon hidden from screen readers", () => {
    render(<StatusPill status="success">Summary ready</StatusPill>);
    const pill = screen.getByText("Summary ready");
    expect(pill.className).toContain("text-success");
    expect(pill.querySelector("svg")).toHaveAttribute("aria-hidden");
  });

  it("processing is neutral grey and announced as a status", () => {
    render(<StatusPill status="processing">Processing</StatusPill>);
    const pill = screen.getByRole("status");
    expect(pill.className).toContain("text-text-secondary");
    expect(pill.className).not.toMatch(/text-(success|warning|error|info)/);
  });

  it("field errors are announced and render nothing when empty", () => {
    const { rerender } = render(<FieldError id="e" message="Title is required" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Title is required");
    rerender(<FieldError id="e" message={null} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
