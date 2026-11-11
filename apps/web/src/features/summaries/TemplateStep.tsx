import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight, Check, Clock, FileText, Layers, List, Pencil, SlidersHorizontal } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Loading, SummaryCardSkeleton } from "@/components/feedback/Skeleton";
import { FieldError } from "@/components/status/FieldError";
import { getPaper, paperKeys } from "@/features/papers/api";
import { formatBytes, formatPages } from "@/features/papers/format";

import { createSummary, listTemplates, summaryKeys } from "./api";

const STEPS = ["Upload", "Template selection", "Processing", "Results"];

function Stepper() {
  return (
    <ol aria-label="Progress" className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
      {STEPS.map((label, index) => (
        <li key={label} className="flex items-center gap-2">
          <span
            aria-hidden
            className={`flex size-8 items-center justify-center rounded-pill border ${
              index === 1 ? "border-primary bg-primary text-primary-text" : "border-border-strong"
            }`}
          >
            {index === 0 ? <Check className="size-4" /> : `0${String(index + 1)}`}
          </span>
          <span className={index === 1 ? "font-medium" : "text-text-secondary"} aria-current={index === 1 ? "step" : undefined}>
            {label}
          </span>
          {index < STEPS.length - 1 && <span aria-hidden className="hidden h-px w-10 bg-border-strong sm:block" />}
        </li>
      ))}
    </ol>
  );
}

function Option({
  selected, onSelect, icon, title, description, meta,
}: {
  selected: boolean; onSelect: () => void; icon: ReactNode; title: string; description: string; meta: ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={`flex h-full flex-col gap-3 rounded-xl border bg-surface p-5 text-left hover:bg-muted ${
        selected ? "border-2 border-text" : "border-border"
      }`}
    >
      <span className="flex items-start justify-between">
        <span className="flex size-12 items-center justify-center rounded-lg bg-muted">{icon}</span>
        <span
          aria-hidden
          className={`flex size-6 items-center justify-center rounded-pill border ${selected ? "border-primary bg-primary text-primary-text" : "border-border-strong"}`}
        >
          {selected && <Check className="size-4" />}
        </span>
      </span>
      <span className="font-display text-xl font-bold">{title}</span>
      <span className="text-text-secondary">{description}</span>
      <span className="mt-auto flex flex-wrap gap-4 border-t border-border pt-3 text-sm text-text-secondary">{meta}</span>
    </button>
  );
}

/** Step 02 of the upload flow (spec 006 AC2, mockup). Indexing runs while the user chooses. */
export default function TemplateStep() {
  const { paperId } = useParams({ from: "/app/papers/$paperId/template" });
  const navigate = useNavigate();
  const paper = useQuery({ queryKey: paperKeys.detail(paperId), queryFn: () => getPaper(paperId) });
  const templates = useQuery({ queryKey: summaryKeys.templates, queryFn: listTemplates });
  const [choice, setChoice] = useState<string | null>(null);
  const system = (templates.data ?? []).filter((t) => t.kind === "system");
  const selected = choice ?? system[0]?.id ?? null;

  const start = useMutation({
    mutationFn: (templateId: string) => createSummary(paperId, templateId),
    onSuccess: () => navigate({ to: "/app/papers/$paperId/processing", params: { paperId } }),
  });

  return (
    <div className="flex flex-col gap-6 px-4 pt-6 pb-10 md:px-8">
      <Stepper />
      <header>
        <h1 className="font-display text-3xl font-bold tracking-tight md:text-4xl">Choose a Summary Template</h1>
        <p className="mt-1 text-text-secondary">Select how you want to extract and organize insights from your paper.</p>
      </header>

      <section aria-label="File" className="flex items-center gap-4 rounded-xl border border-border bg-surface p-4">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-muted">
          <FileText aria-hidden className="size-6" />
        </span>
        <div className="min-w-0">
          <p className="truncate font-medium">{paper.data?.filename ?? " "}</p>
          <p className="text-sm text-text-secondary">
            {[paper.data?.pages ? formatPages(paper.data.pages) : null, paper.data ? formatBytes(paper.data.size_bytes) : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
      </section>

      {templates.isPending ? (
        <Loading label="Loading templates">
          <SummaryCardSkeleton />
        </Loading>
      ) : (
        <div role="radiogroup" aria-label="Summary template" className="grid gap-4 md:grid-cols-3">
          {system.map((t, index) => (
            <Option
              key={t.id}
              selected={selected === t.id}
              onSelect={() => {
                setChoice(t.id);
              }}
              icon={index === 0 ? <FileText aria-hidden className="size-6" /> : <List aria-hidden className="size-6" />}
              title={t.name}
              description={
                index === 0
                  ? "Summarize the paper with the core problem, approach, key findings, and conclusion."
                  : "A comprehensive summary with research gap, methodology, dataset, results, limitations, and future work."
              }
              meta={
                <>
                  <span className="flex items-center gap-1.5">
                    {index === 0 ? <Clock aria-hidden className="size-4" /> : <Layers aria-hidden className="size-4" />}
                    {index === 0 ? "Fast" : "In-depth"}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <List aria-hidden className="size-4" />
                    {`${String(t.fields.length)} sections`}
                  </span>
                </>
              }
            />
          ))}
          <Link
            to="/app/templates"
            className="flex h-full flex-col gap-3 rounded-xl border border-border bg-surface p-5 hover:bg-muted"
          >
            <span className="flex size-12 items-center justify-center rounded-lg bg-muted">
              <SlidersHorizontal aria-hidden className="size-6" />
            </span>
            <span className="font-display text-xl font-bold">Custom Template</span>
            <span className="text-text-secondary">Create and manage your own summary structure by defining the sections you need.</span>
            <span className="mt-auto flex gap-4 border-t border-border pt-3 text-sm text-text-secondary">
              <span className="flex items-center gap-1.5">
                <Pencil aria-hidden className="size-4" />
                Flexible
              </span>
              <span className="flex items-center gap-1.5">
                <Layers aria-hidden className="size-4" />
                Fully customizable
              </span>
            </span>
          </Link>
        </div>
      )}

      <FieldError id="template-error" message={start.error?.message} />
      <div className="flex items-center justify-between gap-4">
        <Link to="/app/library" className="inline-flex min-h-11 items-center gap-2 rounded-pill border border-border px-5 hover:bg-muted">
          <ArrowLeft aria-hidden className="size-5" />
          Back
        </Link>
        <button
          type="button"
          disabled={!selected || start.isPending}
          onClick={() => {
            if (selected) start.mutate(selected);
          }}
          className="inline-flex min-h-11 items-center gap-2 rounded-pill bg-primary px-6 font-medium text-primary-text disabled:opacity-50"
        >
          Continue
          <ArrowRight aria-hidden className="size-5" />
        </button>
      </div>
    </div>
  );
}
