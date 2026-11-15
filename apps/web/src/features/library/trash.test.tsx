import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { Toaster } from "@/components/status/Toaster";
import { getFlags } from "@/features/flags/client";
import { deletePaper, PaperInTrashError } from "@/features/papers/api";
import { paper } from "@/features/papers/fixtures";
import { InTrashDialog } from "@/features/papers/InTrashDialog";
import type { useUploadFlow } from "@/features/papers/useUploadFlow";
import { createAppRouter } from "@/router";
import { seriousViolations } from "@/test/axe";

import { deleteForever, emptyTrash, listCollections, listLibrary, listTrash, restorePaper } from "./api";
import { deletesIn } from "./format";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() =>
    Promise.resolve({
      user: { id: "u1", email: "ada@example.org", display_name: "Ada", platform_role: "user" },
      org: { id: "o1", name: "Ada workspace", kind: "personal" },
      role: "owner",
    }),
  ),
}));
vi.mock("@/features/flags/client", () => ({ getFlags: vi.fn() }));
vi.mock("@/features/papers/api", async (orig) => ({
  ...(await orig<typeof import("@/features/papers/api")>()),
  deletePaper: vi.fn(),
}));
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  listLibrary: vi.fn(),
  listCollections: vi.fn(),
  listTrash: vi.fn(),
  restorePaper: vi.fn(),
  deleteForever: vi.fn(),
  emptyTrash: vi.fn(),
}));

const DAY = 24 * 60 * 60 * 1000;

function binned(id: string, title: string, daysLeft: number) {
  const purge = new Date(Date.now() + daysLeft * DAY - 60_000);
  return { id, title, deleted_at: new Date(purge.getTime() - 7 * DAY).toISOString(), purge_at: purge.toISOString() };
}

async function renderAt(path: string) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
  await router.load();
  return { router, container: view.container };
}

beforeEach(() => {
  setAuthState({ status: "signed-in", provider: "dev" });
  vi.mocked(getFlags).mockResolvedValue({ recently_deleted: true });
  vi.mocked(listLibrary).mockResolvedValue({ items: [paper()], next_cursor: null });
  vi.mocked(listCollections).mockResolvedValue([]);
  vi.mocked(listTrash).mockResolvedValue([binned("t1", "Attention Is All You Need", 3), binned("t2", "LoRA", 1)]);
  vi.mocked(restorePaper).mockResolvedValue(paper());
  vi.mocked(deleteForever).mockResolvedValue();
  vi.mocked(emptyTrash).mockResolvedValue(2);
  vi.mocked(deletePaper).mockResolvedValue();
});

describe("Recently deleted (spec 019)", () => {
  it("AC3: the filter lists binned papers with the days left", async () => {
    const { container } = await renderAt("/app/library?trash=true");
    expect(await screen.findByRole("heading", { level: 1, name: "Recently deleted" })).toBeInTheDocument();
    const rows = within(await screen.findByRole("list", { name: "Recently deleted" })).getAllByRole("listitem");
    expect(within(rows[0] as HTMLElement).getByText("Deletes in 3 days")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText("Deletes in 1 day")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recently deleted" })).toHaveAttribute("aria-pressed", "true");
    expect(listLibrary).not.toHaveBeenCalled();
    expect(await seriousViolations(container)).toEqual([]);
  });

  it("AC3: an empty bin says how long papers stay", async () => {
    vi.mocked(listTrash).mockResolvedValue([]);
    await renderAt("/app/library?trash=true");
    expect(await screen.findByText("Nothing here")).toBeInTheDocument();
  });

  it("AC4: Restore brings a paper back", async () => {
    await renderAt("/app/library?trash=true");
    fireEvent.click(await screen.findByRole("button", { name: "Restore LoRA" }));
    await waitFor(() => { expect(restorePaper).toHaveBeenCalledWith("t2"); });
    expect(await screen.findByText("Paper restored.")).toBeInTheDocument();
  });

  it("AC5: Delete forever asks first, and Empty clears the bin", async () => {
    await renderAt("/app/library?trash=true");
    fireEvent.click(await screen.findByRole("button", { name: "Actions for LoRA" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete forever" }));
    const dialog = screen.getByRole("dialog", { name: "Delete forever?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete forever" }));
    await waitFor(() => { expect(deleteForever).toHaveBeenCalledWith("t2"); });

    fireEvent.click(screen.getByRole("button", { name: "Empty" }));
    const confirm = screen.getByRole("dialog", { name: "Empty Recently deleted?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete all forever" }));
    await waitFor(() => { expect(emptyTrash).toHaveBeenCalled(); });
  });

  it("AC2: deleting offers Undo, which restores the paper", async () => {
    await renderAt("/app/library");
    const rows = within(await screen.findByRole("list", { name: "Papers" })).getAllByRole("listitem");
    fireEvent.click(within(rows[0] as HTMLElement).getByRole("button", { name: /Actions for/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "Delete paper?" })).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Moved to Recently deleted.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => { expect(restorePaper).toHaveBeenCalledWith(paper().id); });
  });

  it("AC12: with the flag off there is no filter and Delete is immediate", async () => {
    vi.mocked(getFlags).mockResolvedValue({ recently_deleted: false });
    await renderAt("/app/library");
    await screen.findByRole("list", { name: "Papers" });
    await waitFor(() => { expect(screen.queryByRole("button", { name: "Recently deleted" })).toBeNull(); });
    const rows = within(screen.getByRole("list", { name: "Papers" })).getAllByRole("listitem");
    fireEvent.click(within(rows[0] as HTMLElement).getByRole("button", { name: /Actions for/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(within(await screen.findByRole("dialog", { name: "Delete paper?" })).getByText(/This cannot be undone/)).toBeInTheDocument();
  });

  it("AC8: a re-upload of a binned paper asks Restore or Upload as new", () => {
    const flow = {
      binned: new PaperInTrashError("up1", "t1", "Attention Is All You Need"),
      resolving: false,
      restoreBinned: vi.fn(),
      uploadAsNew: vi.fn(),
      dismissBinned: vi.fn(),
    } as unknown as ReturnType<typeof useUploadFlow>;
    render(<InTrashDialog flow={flow} />);
    const dialog = screen.getByRole("dialog", { name: "This paper is in Recently deleted" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Restore" }));
    expect(flow.restoreBinned).toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Upload as new" }));
    expect(flow.uploadAsNew).toHaveBeenCalled();
  });

  it("AC3: days left come from the server's purge time", () => {
    const now = Date.parse("2026-11-15T12:00:00Z");
    expect(deletesIn("2026-11-18T11:00:00Z", now)).toBe("Deletes in 3 days");
    expect(deletesIn("2026-11-16T11:00:00Z", now)).toBe("Deletes in 1 day");
    expect(deletesIn("2026-11-15T11:00:00Z", now)).toBe("Deletes today");
  });
});
