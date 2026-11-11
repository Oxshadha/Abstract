import { act, render, screen } from "@testing-library/react";
import { FileText } from "lucide-react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EmptyState } from "./EmptyState";
import { OfflineBanner } from "./offline";
import { useOnline } from "./useOnline";
import { ListRowSkeleton, Loading } from "./Skeleton";

afterEach(() => {
  vi.restoreAllMocks();
});

function setOnline(value: boolean) {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(value);
  act(() => {
    window.dispatchEvent(new Event(value ? "online" : "offline"));
  });
}

describe("AC14: skeleton, empty and offline states", () => {
  it("skeletons announce one loading status and hide their shapes", () => {
    const { container } = render(
      <Loading label="Loading papers">
        <ListRowSkeleton />
      </Loading>,
    );
    expect(screen.getByRole("status", { name: "Loading papers" })).toHaveAttribute("aria-busy", "true");
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThan(0);
  });

  it("empty state shows title, description and one action", () => {
    render(
      <EmptyState
        icon={FileText}
        title="No papers yet"
        description="Upload a research paper to get a structured summary."
        action={<button type="button">Choose PDF</button>}
      />,
    );
    expect(screen.getByRole("heading", { name: "No papers yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose PDF" })).toBeInTheDocument();
  });

  it("offline banner appears and disappears with the connection", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    function SaveButton() {
      const online = useOnline();
      return (
        <button type="button" disabled={!online}>
          Save
        </button>
      );
    }
    render(
      <>
        <OfflineBanner />
        <SaveButton />
      </>,
    );
    expect(screen.queryByText(/you are offline/i)).toBeNull();
    setOnline(false);
    expect(screen.getByText(/you are offline/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    setOnline(true);
    expect(screen.queryByText(/you are offline/i)).toBeNull();
  });
});
