import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setAuthState } from "@/auth/state";
import { Toaster } from "@/components/status/Toaster";
import { listLibrary } from "@/features/library/api";
import { paper } from "@/features/papers/fixtures";
import { listTemplates } from "@/features/summaries/api";
import { createAppRouter } from "@/router";
import { seriousViolations } from "@/test/axe";

import { StaleTemplateError, createTemplate, getLimits, getTemplate, previewTemplate, saveTemplate, type Template } from "./api";
import { exportJson, importJson } from "./fields";

vi.mock("@/api/me", () => ({
  fetchMe: vi.fn(() =>
    Promise.resolve({
      user: { id: "u1", email: "ada@example.org", display_name: "Ada", platform_role: "user" },
      org: { id: "o1", name: "Ada workspace", kind: "personal" },
      role: "owner",
    }),
  ),
}));
vi.mock("@/features/summaries/api", async (orig) => ({ ...(await orig<typeof import("@/features/summaries/api")>()), listTemplates: vi.fn() }));
vi.mock("@/features/library/api", async (orig) => ({ ...(await orig<typeof import("@/features/library/api")>()), listLibrary: vi.fn(), listCollections: vi.fn(() => Promise.resolve([])) }));
vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  getTemplate: vi.fn(),
  getLimits: vi.fn(),
  createTemplate: vi.fn(),
  saveTemplate: vi.fn(),
  previewTemplate: vi.fn(),
}));

const QUICK: Template = {
  id: "00000000-0000-4000-8000-000000000001",
  kind: "system",
  name: "Quick Summary",
  description: "Problem, approach, key findings, and conclusion.",
  version: 1,
  version_id: "v1",
  fields: [{ key: "abstract", label: "Abstract", instruction: "The abstract.", style: "paragraph", required: true }],
};
const MINE: Template = {
  ...QUICK,
  id: "11111111-1111-4111-8111-111111111111",
  kind: "custom",
  name: "Methods review",
  version: 2,
  fields: [
    { key: "dataset", label: "Dataset", instruction: "Datasets used.", style: "bullets", required: true },
    { key: "metrics", label: "Metrics", instruction: "Metrics reported.", style: "paragraph", required: true },
  ],
};

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
  localStorage.clear();
  vi.mocked(listTemplates).mockResolvedValue([QUICK, MINE]);
  vi.mocked(getLimits).mockResolvedValue({ fields_per_template: 10, custom_templates: 10, label_chars: 60, instruction_chars: 500 });
  vi.mocked(getTemplate).mockResolvedValue(MINE);
  vi.mocked(listLibrary).mockResolvedValue({ items: [paper()], next_cursor: null });
});

describe("Templates page (spec 010 AC1)", () => {
  it("lists the user's templates to edit and system templates to duplicate", async () => {
    await renderAt("/app/templates");
    const mine = await screen.findByRole("list", { name: "Your templates" });
    expect(within(mine).getByText("Methods review")).toBeInTheDocument();
    expect(within(mine).getByText(/2 fields/)).toBeInTheDocument();
    const system = screen.getByRole("list", { name: "System templates" });
    expect(within(system).getByRole("button", { name: "Duplicate to customize: Quick Summary" })).toBeInTheDocument();
  });

  it("has no serious accessibility violations", async () => {
    const { container } = await renderAt("/app/templates");
    await screen.findByRole("list", { name: "Your templates" });
    expect(await seriousViolations(container)).toEqual([]);
  });
});

describe("Builder (spec 010 AC3, AC9, AC10, AC7)", () => {
  it("AC9: checks the same limits as the API before saving", async () => {
    await renderAt("/app/templates/new");
    fireEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByText("Give the template a name.")).toBeInTheDocument();
    expect(screen.getByText("Add a label.")).toBeInTheDocument();
    expect(createTemplate).not.toHaveBeenCalled();
  });

  it("AC3: reorders with the phone buttons and keeps keys of existing fields", async () => {
    vi.mocked(saveTemplate).mockResolvedValue({ ...MINE, version: 3 });
    await renderAt(`/app/templates/${MINE.id}`);
    fireEvent.click(await screen.findByRole("button", { name: "Move Metrics up" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => { expect(saveTemplate).toHaveBeenCalled(); });
    const [, base, body] = vi.mocked(saveTemplate).mock.calls[0] ?? [];
    expect(base).toBe(2);
    expect(body?.fields.map((f) => f.key)).toEqual(["metrics", "dataset"]);
  });

  it("AC9: Add field stops at the limit with the reason", async () => {
    vi.mocked(getTemplate).mockResolvedValue({
      ...MINE,
      fields: Array.from({ length: 10 }, (_, i) => ({ key: `f${String(i)}x`, label: `Field ${String(i)}`, instruction: "x", style: "paragraph" as const, required: true })),
    });
    await renderAt(`/app/templates/${MINE.id}`);
    expect(await screen.findByRole("button", { name: "Add field" })).toBeDisabled();
    expect(screen.getByText("Templates can have up to 10 fields.")).toBeInTheDocument();
  });

  it("AC10: a save from another tab offers to load the newer version or save anyway", async () => {
    vi.mocked(saveTemplate).mockRejectedValueOnce(new StaleTemplateError(3)).mockResolvedValueOnce({ ...MINE, version: 4 });
    await renderAt(`/app/templates/${MINE.id}`);
    fireEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByRole("dialog", { name: "Changed in another tab" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save mine anyway" }));
    await waitFor(() => { expect(vi.mocked(saveTemplate).mock.calls[1]?.[1]).toBe(3); });
  });

  it("AC7: Try on a paper streams fields into the preview", async () => {
    vi.mocked(previewTemplate).mockImplementation(async (_paper, _template, onField) => {
      onField({ key: "dataset", value: "WMT 2014 English-German.", status: "found", evidence: [] });
      await Promise.resolve();
    });
    await renderAt(`/app/templates/${MINE.id}`);
    fireEvent.click(await screen.findByRole("button", { name: "Run" }));
    const preview = await screen.findByRole("list", { name: "Preview" });
    expect(within(preview).getByText("WMT 2014 English-German.")).toBeInTheDocument();
    expect(within(preview).getByText("Dataset")).toBeInTheDocument();
  });
});

describe("Import and export (spec 010 AC12)", () => {
  it("round-trips a template without keys and rejects other files", () => {
    const text = exportJson({ name: "Mine", description: "", fields: [{ id: "a", key: "dataset", label: "Dataset", instruction: "Data.", style: "bullets", required: false }] });
    expect(text).not.toContain("dataset\"");
    const back = importJson(text);
    expect(back.fields[0]).toMatchObject({ key: null, label: "Dataset", style: "bullets", required: false });
    expect(() => importJson('{"hello": 1}')).toThrow("This file is not a template export.");
  });
});
