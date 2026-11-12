import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  AlertCircle,
  BarChart3,
  BookOpen,
  Compass,
  Database,
  Download,
  FileDown,
  FileText,
  Flag,
  Gauge,
  Layers,
  Pencil,
  Quote,
  Plus,
  RotateCcw,
  Search,
  Settings,
  Target,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { SummaryCardSkeleton } from "@/components/feedback/Skeleton";
import { Menu } from "@/components/menu/Menu";
import { Select } from "@/components/menu/Select";
import { StatusPill } from "@/components/status/StatusPill";
import { toast } from "@/components/status/toast";
import { useFlag } from "@/features/flags/api";
import { saveBlob } from "@/lib/download";

import {
  StaleVersionError,
  createSummary,
  editField,
  exportSummary,
  listSummaries,
  listTemplates,
  resetField,
  retrySummary,
  summaryKeys,
  type ExportFormat,
  type Summary,
  type SummaryField,
} from "./api";
import { useCitations } from "@/features/viewer/citation-context";

import { Markdown } from "./Markdown";
import { pageLabel } from "./pages";
import { useSummary } from "./useSummary";

const ICONS: Record<string, LucideIcon> = {
  abstract: BookOpen,
  problem_statement: Flag,
  methodology: Settings,
  key_results: BarChart3,
  conclusion: Target,
  research_gap: Search,
  dataset: Database,
  evaluation: Gauge,
  limitations: AlertCircle,
  future_work: Compass,
};

function FieldCard({ field }: { field: SummaryField }) {
  const Icon = ICONS[field.key] ?? FileText;
  const [open, setOpen] = useState(false);
  const viewer = useCitations();
  const firstEvidence = field.evidence.find((e) => e.page != null && e.verified) ?? field.evidence.find((e) => e.page != null);
  const pages = field.evidence.map((e) => e.page).filter((p): p is number => p != null);
  return (
    <article className="border-b border-border pb-5 last:border-b-0">
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <Icon aria-hidden className="size-5" />
        <h3 className="font-display text-lg font-bold">{field.label}</h3>
        <span className="ml-auto flex flex-wrap gap-1.5">
          {field.status === "not_reported" ? (
            <StatusPill status="neutral">Not reported</StatusPill>
          ) : field.verification === "verified" ? (
            <StatusPill status="success">Verified</StatusPill>
          ) : (
            <StatusPill status="neutral">Provisional</StatusPill>
          )}
          {field.status === "inferred" && <StatusPill status="info">Inferred</StatusPill>}
          {field.edited && <StatusPill status="neutral">Edited</StatusPill>}
        </span>
      </header>
      <Markdown>{field.value}</Markdown>
      {pages.length > 0 && (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => {
            setOpen(!open);
            // Spec 008 AC4: open the cited page with the sentence highlighted.
            if (!open && firstEvidence?.page != null) viewer?.open(firstEvidence.page, firstEvidence.quote);
          }}
          className="mt-2 inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border px-2.5 text-sm hover:bg-muted"
        >
          <BookOpen aria-hidden className="size-4" />
          {`Source: ${pageLabel(pages)}`}
        </button>
      )}
      {open && (
        <ul className="mt-2 flex flex-col gap-2" aria-label={`Evidence for ${field.label}`}>
          {field.evidence.map((e, i) => (
            <li key={i} className="rounded-md bg-muted p-2.5 text-sm">
              <q className="font-reading">{e.quote}</q>
              <span className="mt-1 flex flex-wrap items-center gap-x-2 text-text-secondary">
                {e.page != null ? `Page ${String(e.page)}` : "Page unknown"}
                {e.verified ? " · found in the paper" : " · not found word for word"}
                {viewer && e.page != null && (
                  <button type="button" onClick={() => { viewer.open(e.page ?? 1, e.quote); }} className="min-h-9 underline">
                    Show in paper
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

type SaveState = "idle" | "saving" | "saved" | "stale" | "error";

function FieldEditor({
  field,
  onSave,
  onReset,
}: {
  field: SummaryField;
  onSave: (value: string) => Promise<void>;
  onReset: () => Promise<void>;
}) {
  const [draft, setDraft] = useState(field.value);
  const timer = useRef<number | null>(null);
  const id = `edit-${field.key}`;
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );
  return (
    <div className="border-b border-border pb-5 last:border-b-0">
      <label htmlFor={id} className="mb-2 flex items-center gap-2 font-display text-lg font-bold">
        {field.label}
        {field.edited && <StatusPill status="neutral">Edited</StatusPill>}
      </label>
      <textarea
        id={id}
        value={draft}
        rows={Math.min(12, Math.max(3, draft.split("\n").length + 1))}
        onChange={(e) => {
          const value = e.target.value;
          setDraft(value);
          if (timer.current !== null) window.clearTimeout(timer.current);
          // AC12: autosave 1 s after typing stops.
          timer.current = window.setTimeout(() => {
            if (value.trim()) void onSave(value);
          }, 1000);
        }}
        className="w-full rounded-md border border-border bg-surface p-3 font-reading"
      />
      {field.edited && (
        <button
          type="button"
          onClick={() => {
            void onReset().then(() => {
              setDraft(field.value);
            });
          }}
          className="mt-1 inline-flex min-h-9 items-center gap-1.5 text-sm text-text-secondary hover:text-text"
        >
          <RotateCcw aria-hidden className="size-4" />
          Reset to the generated text
        </button>
      )}
    </div>
  );
}

function TemplateSwitcher({
  current,
  onChoose,
}: {
  current: string | null;
  onChoose: (templateId: string) => void;
}) {
  const templates = useQuery({ queryKey: summaryKeys.templates, queryFn: listTemplates });
  return (
    <Select
      label="Summary template"
      value={current ?? ""}
      placeholder="Quick Summary"
      icon={<Layers aria-hidden className="size-4 shrink-0" />}
      options={(templates.data ?? []).map((t) => ({ value: t.id, label: t.name, description: t.description }))}
      onChange={onChoose}
      width="w-72"
      footer={
        <Link to="/app/templates" className="mt-1 flex min-h-11 items-start gap-2 rounded-md border-t border-border p-2 text-sm hover:bg-muted">
          <Plus aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="block font-medium">Custom Template</span>
            <span className="block text-text-secondary">Create and manage your own summary structure.</span>
          </span>
        </Link>
      }
    />
  );
}

function SummaryBody({ summary }: { summary: Summary }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [save, setSave] = useState<SaveState>("idle");
  const version = useRef(summary.version);
  useEffect(() => {
    if (save !== "saving") version.current = Math.max(version.current, summary.version);
  }, [summary.version, save]);

  const retry = useMutation({
    mutationFn: () => retrySummary(summary.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: summaryKeys.detail(summary.id) }),
  });

  const persist = async (call: () => Promise<number>) => {
    setSave("saving");
    try {
      version.current = await call();
      setSave("saved");
    } catch (err) {
      setSave(err instanceof StaleVersionError ? "stale" : "error");
    }
  };

  const generating = summary.status === "queued" || summary.status === "generating";
  const pending = Math.max(0, summary.expected_fields - summary.fields.length);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-2">
        <p aria-live="polite" className="text-sm text-text-secondary">
          {generating ? "Building your summary" : save === "saving" ? "Saving" : save === "saved" ? "Saved" : ""}
        </p>
        {summary.status === "ready" && (
          <button
            type="button"
            aria-pressed={editing}
            onClick={() => {
              setEditing(!editing);
            }}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 hover:bg-muted"
          >
            <Pencil aria-hidden className="size-4" />
            {editing ? "Done" : "Edit"}
          </button>
        )}
      </div>

      {save === "stale" && (
        <div role="alert" className="rounded-md border border-border p-3 text-sm">
          This summary changed in another tab.
          <span className="mt-2 flex gap-2">
            <button
              type="button"
              className="min-h-9 rounded-md border border-border px-3 hover:bg-muted"
              onClick={() => {
                setSave("idle");
                void queryClient.invalidateQueries({ queryKey: summaryKeys.detail(summary.id) });
              }}
            >
              Reload
            </button>
          </span>
        </div>
      )}
      {save === "error" && <p role="alert" className="text-sm">Your last edit was not saved. Please try again.</p>}

      {summary.status === "failed" && (
        <div className="flex flex-col items-start gap-2 rounded-md border border-border p-4">
          <StatusPill status="error">Failed</StatusPill>
          <p>{summary.error_message}</p>
          <button
            type="button"
            disabled={retry.isPending}
            onClick={() => {
              retry.mutate();
            }}
            className="inline-flex min-h-11 items-center gap-2 rounded-pill bg-primary px-5 text-primary-text disabled:opacity-50"
          >
            <RotateCcw aria-hidden className="size-4" />
            Retry
          </button>
        </div>
      )}

      {summary.fields.map((field) =>
        editing ? (
          <FieldEditor
            key={field.key}
            field={field}
            onSave={(value) => persist(() => editField(summary.id, field.key, value, version.current))}
            onReset={() => persist(() => resetField(summary.id, field.key, version.current))}
          />
        ) : (
          <FieldCard key={field.key} field={field} />
        ),
      )}
      {generating &&
        Array.from({ length: pending }, (_, i) => (
          <div key={i} role="status" aria-label="Loading a summary section">
            <SummaryCardSkeleton />
          </div>
        ))}
    </div>
  );
}

/** Workspace Summary panel (spec 006 AC8, mockup). */
/** Spec 015 AC6: Markdown, a branded PDF made by the server, or the paper's BibTeX entry. */
function ExportMenu({ summary }: { summary: Summary | undefined }) {
  const ready = summary?.status === "ready";
  const download = async (format: ExportFormat) => {
    if (!summary) return;
    try {
      const file = await exportSummary(summary.id, format);
      saveBlob(file.blob, file.filename);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Could not export the summary.");
    }
  };
  const item = (format: ExportFormat, label: string, icon: ReactNode) => ({
    label,
    icon,
    disabled: !ready,
    onSelect: () => void download(format),
  });
  return (
    <Menu
      label="Export"
      trigger={<Download aria-hidden className="size-5" />}
      items={[
        item("pdf", "PDF", <FileDown aria-hidden className="size-4" />),
        item("md", "Markdown", <FileText aria-hidden className="size-4" />),
        item("bib", "Citation (BibTeX)", <Quote aria-hidden className="size-4" />),
      ]}
      footer={
        ready ? null : (
          <p className="px-2 py-1.5 text-xs text-text-secondary">
            {summary ? "Export opens when the summary is finished." : "Create a summary to export it."}
          </p>
        )
      }
    />
  );
}

export function SummaryPanel({ paperId }: { paperId: string }) {
  const readingAids = useFlag("reading_aids"); // spec 011 AC7: export
  const queryClient = useQueryClient();
  const summaries = useQuery({ queryKey: summaryKeys.forPaper(paperId), queryFn: () => listSummaries(paperId) });
  const templates = useQuery({ queryKey: summaryKeys.templates, queryFn: listTemplates });
  const [chosen, setChosen] = useState<string | null>(null);
  const templateId = chosen ?? summaries.data?.[0]?.template_id ?? templates.data?.[0]?.id ?? null;
  // The newest summary for this template (an "Update summary" adds one per template version).
  const brief =
    summaries.data
      ?.filter((s) => s.template_id === templateId)
      .sort((a, b) => b.template_version - a.template_version)[0] ?? null;
  const outdated = Boolean(brief?.template_latest_version && brief.template_latest_version > brief.template_version);
  const summary = useSummary(brief?.id ?? null);

  const start = useMutation({
    mutationFn: (id: string) => createSummary(paperId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: summaryKeys.forPaper(paperId) }),
  });

  const choose = (id: string) => {
    setChosen(id);
    // Switching to a template without a summary starts one (AC8).
    if (!summaries.data?.some((s) => s.template_id === id)) start.mutate(id);
  };

  return (
    // The heading and template switcher stay put; only the summary scrolls (design principle 5).
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex shrink-0 items-center justify-between gap-2">
        <h2 className="font-display text-lg font-bold whitespace-nowrap">Summary</h2>
        <span className="flex min-w-0 items-center gap-1">
          <TemplateSwitcher current={templateId} onChoose={choose} />
          {readingAids && <ExportMenu summary={summary.data} />}
        </span>
      </div>
      <div className="-mx-1 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-1 max-lg:pb-28">
      {outdated && templateId && (
        // Spec 010 AC5: the template changed since this summary; updating is the user's choice.
        <div role="status" className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted p-3 text-sm">
          <span className="min-w-0 flex-1">A newer version of this template exists.</span>
          <button
            type="button"
            disabled={start.isPending}
            onClick={() => { start.mutate(templateId); }}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border bg-surface px-3 hover:bg-muted disabled:opacity-50"
          >
            <RotateCcw aria-hidden className="size-4" />
            Update summary
          </button>
        </div>
      )}
      {summaries.isPending || (brief && summary.isPending) ? (
        <div role="status" aria-label="Loading the summary" className="flex flex-col gap-3">
          <SummaryCardSkeleton />
          <SummaryCardSkeleton />
        </div>
      ) : summary.data ? (
        <SummaryBody summary={summary.data} />
      ) : (
        <div className="flex flex-col items-start gap-3 rounded-md border border-dashed border-border-strong p-4">
          <p className="text-text-secondary">No summary yet for this template.</p>
          <button
            type="button"
            disabled={!templateId || start.isPending}
            onClick={() => {
              if (templateId) start.mutate(templateId);
            }}
            className="inline-flex min-h-11 items-center gap-2 rounded-pill bg-primary px-5 text-primary-text disabled:opacity-50"
          >
            Create summary
          </button>
        </div>
      )}
      </div>
    </div>
  );
}
