import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { HttpError, shouldRetry } from "@/lib/queryClient";

import { ErrorBoundary } from "./ErrorBoundary";

describe("AC9: query retry policy", () => {
  it("never retries 4xx, retries network/5xx at most twice", () => {
    expect(shouldRetry(0, new HttpError(404, "x"))).toBe(false);
    expect(shouldRetry(0, new HttpError(401, "x"))).toBe(false);
    expect(shouldRetry(0, new HttpError(503, "x"))).toBe(true);
    expect(shouldRetry(1, new TypeError("Failed to fetch"))).toBe(true);
    expect(shouldRetry(2, new TypeError("Failed to fetch"))).toBe(false);
  });
});

let shouldThrow = true;
function Flaky() {
  if (shouldThrow) throw new Error("panel exploded");
  return <p>Panel content</p>;
}

describe("AC11: error boundaries", () => {
  it("contains a crash to its panel and recovers with Try again", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined); // React logs caught errors
    function Page() {
      const [, setTick] = useState(0);
      return (
        <div>
          <p>Other panel</p>
          <ErrorBoundary name="the summary">
            <Flaky />
          </ErrorBoundary>
          <button type="button" onClick={() => { setTick((t) => t + 1); }}>rerender</button>
        </div>
      );
    }
    render(<Page />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong in the summary.");
    expect(screen.getByText("Other panel")).toBeInTheDocument();
    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByText("Panel content")).toBeInTheDocument();
  });
});
